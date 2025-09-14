import os
import json
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from typing import List
from dotenv import load_dotenv

from models import Order, OrderCreate, OrderUpdate
from database import Database, get_database
from websocket_manager import manager

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global database instance
db: Database = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global db
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is required")
    
    db = Database(database_url)
    await db.initialize()
    logger.info("Application started")
    
    yield
    
    # Shutdown
    await db.close()
    logger.info("Application shutdown")

# Create FastAPI app
app = FastAPI(
    title="Real-Time Orders API",
    description="Real-time database updates system with WebSocket support",
    version="1.0.0",
    lifespan=lifespan
)

# Mount static files (client)
app.mount("/static", StaticFiles(directory="../client"), name="static")

# Dependency to get database instance
async def get_db():
    return db

# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    
    try:
        # Send initial data to new client
        orders = await db.get_all_orders()
        await manager.send_json_personal({
            "type": "initial_data",
            "data": orders
        }, websocket)
        
        while True:
            # Receive messages from client
            data = await websocket.receive_json()
            message_type = data.get("type")
            
            if message_type == "create_order":
                try:
                    order_data = data.get("data", {})
                    order = OrderCreate(**order_data)
                    await db.create_order(order)
                except Exception as e:
                    await manager.send_json_personal({
                        "type": "error",
                        "message": f"Failed to create order: {str(e)}"
                    }, websocket)
            
            elif message_type == "update_order":
                try:
                    order_id = data.get("id")
                    updates = data.get("updates", {})
                    order_update = OrderUpdate(**updates)
                    await db.update_order(order_id, order_update)
                except Exception as e:
                    await manager.send_json_personal({
                        "type": "error",
                        "message": f"Failed to update order: {str(e)}"
                    }, websocket)
            
            elif message_type == "delete_order":
                try:
                    order_id = data.get("id")
                    await db.delete_order(order_id)
                except Exception as e:
                    await manager.send_json_personal({
                        "type": "error",
                        "message": f"Failed to delete order: {str(e)}"
                    }, websocket)
                    
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)

# REST API Endpoints
@app.get("/")
async def get_client():
    """Serve the client HTML page"""
    with open("../client/index.html", "r") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

@app.get("/api/orders", response_model=List[dict])
async def get_orders(database: Database = Depends(get_db)):
    """Get all orders"""
    try:
        orders = await database.get_all_orders()
        return orders
    except Exception as e:
        logger.error(f"Error fetching orders: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch orders")

@app.post("/api/orders", response_model=dict)
async def create_order(order: OrderCreate, database: Database = Depends(get_db)):
    """Create a new order"""
    try:
        new_order = await database.create_order(order)
        return new_order
    except Exception as e:
        logger.error(f"Error creating order: {e}")
        raise HTTPException(status_code=500, detail="Failed to create order")

@app.get("/api/orders/{order_id}", response_model=dict)
async def get_order(order_id: int, database: Database = Depends(get_db)):
    """Get a specific order"""
    try:
        order = await database.get_order_by_id(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        return order
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching order: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch order")

@app.put("/api/orders/{order_id}", response_model=dict)
async def update_order(order_id: int, order_update: OrderUpdate, database: Database = Depends(get_db)):
    """Update an existing order"""
    try:
        updated_order = await database.update_order(order_id, order_update)
        if not updated_order:
            raise HTTPException(status_code=404, detail="Order not found")
        return updated_order
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating order: {e}")
        raise HTTPException(status_code=500, detail="Failed to update order")

@app.delete("/api/orders/{order_id}")
async def delete_order(order_id: int, database: Database = Depends(get_db)):
    """Delete an order"""
    try:
        deleted_order = await database.delete_order(order_id)
        if not deleted_order:
            raise HTTPException(status_code=404, detail="Order not found")
        return {"message": "Order deleted successfully", "order": deleted_order}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting order: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete order")

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "connected_clients": manager.connection_count,
        "database": "connected" if db else "disconnected"
    }

if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=True,
        log_level="info"
    )

