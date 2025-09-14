import asyncio
import asyncpg
import json
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from models import Order, OrderCreate, OrderUpdate, DatabaseChange
from websocket_manager import manager

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.pool: Optional[asyncpg.Pool] = None
        self.listener_connection: Optional[asyncpg.Connection] = None
        self.listening_task: Optional[asyncio.Task] = None

    async def initialize(self):
        """Initialize database connection pool and setup listener"""
        try:
            # Create connection pool
            self.pool = await asyncpg.create_pool(
                self.database_url,
                min_size=2,
                max_size=10,
                command_timeout=60
            )
            logger.info("Database connection pool created")

            # Setup notification listener
            await self.setup_notification_listener()
            logger.info("Database initialized successfully")

        except Exception as e:
            logger.error(f"Database initialization error: {e}")
            raise

    async def setup_notification_listener(self):
        """Setup PostgreSQL LISTEN for order changes"""
        try:
            self.listener_connection = await asyncpg.connect(self.database_url)
            await self.listener_connection.add_listener('order_changes', self.handle_notification)
            logger.info("Listening for order changes...")

        except Exception as e:
            logger.error(f"Error setting up notification listener: {e}")
            raise

    async def handle_notification(self, connection, pid, channel, payload):
        """Handle PostgreSQL notifications"""
        try:
            change_data = json.loads(payload)
            logger.info(f"Database change detected: {change_data['operation']}")
            
            # Broadcast to all connected WebSocket clients
            await manager.broadcast_json({
                "type": "database_change",
                "data": change_data
            })

        except Exception as e:
            logger.error(f"Error processing notification: {e}")

    async def get_all_orders(self) -> List[Dict]:
        """Get all orders ordered by updated_at DESC"""
        query = """
            SELECT id, customer_name, product_name, status, updated_at 
            FROM orders 
            ORDER BY updated_at DESC
        """
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(query)
            return [dict(row) for row in rows]

    async def create_order(self, order: OrderCreate) -> Dict:
        """Create a new order"""
        query = """
            INSERT INTO orders (customer_name, product_name, status) 
            VALUES ($1, $2, $3) 
            RETURNING id, customer_name, product_name, status, updated_at
        """
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                query, 
                order.customer_name, 
                order.product_name, 
                order.status
            )
            return dict(row)

    async def update_order(self, order_id: int, order_update: OrderUpdate) -> Optional[Dict]:
        """Update an existing order"""
        # Build dynamic update query
        update_fields = []
        values = []
        param_count = 1

        if order_update.customer_name is not None:
            update_fields.append(f"customer_name = ${param_count}")
            values.append(order_update.customer_name)
            param_count += 1

        if order_update.product_name is not None:
            update_fields.append(f"product_name = ${param_count}")
            values.append(order_update.product_name)
            param_count += 1

        if order_update.status is not None:
            update_fields.append(f"status = ${param_count}")
            values.append(order_update.status)
            param_count += 1

        if not update_fields:
            return None

        query = f"""
            UPDATE orders 
            SET {', '.join(update_fields)}
            WHERE id = ${param_count}
            RETURNING id, customer_name, product_name, status, updated_at
        """
        values.append(order_id)

        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(query, *values)
            return dict(row) if row else None

    async def delete_order(self, order_id: int) -> Optional[Dict]:
        """Delete an order"""
        query = """
            DELETE FROM orders 
            WHERE id = $1 
            RETURNING id, customer_name, product_name, status, updated_at
        """
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(query, order_id)
            return dict(row) if row else None

    async def get_order_by_id(self, order_id: int) -> Optional[Dict]:
        """Get a single order by ID"""
        query = """
            SELECT id, customer_name, product_name, status, updated_at 
            FROM orders 
            WHERE id = $1
        """
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(query, order_id)
            return dict(row) if row else None

    async def close(self):
        """Close database connections"""
        if self.listening_task:
            self.listening_task.cancel()
        
        if self.listener_connection:
            await self.listener_connection.close()
        
        if self.pool:
            await self.pool.close()
        
        logger.info("Database connections closed")

# Global database instance
db: Optional[Database] = None

async def get_database() -> Database:
    return db