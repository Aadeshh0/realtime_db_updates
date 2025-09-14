CREATE TABLE orders(
    id SERIAL PRIMARY KEY,
    customer_name VARCHAR(255) NOT NULL,
    product_name VARCHAR(255) NOT NULL, 
    status VARCHAR(255) CHECK (status IN ('pending', 'shipped', 'delivered')),
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE OR REPLACE FUNCTION notify_any_orders_changes()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        PERFORM pg_notify('order_changes', json_build_object(
            'operation', 'INSERT',
            'data', row_to_json(NEW)
        )::text);
        RETURN NEW;
    ELSIF TG_OP = 'UPDATE' THEN
        PERFORM pg_notify('order_changes', json_build_object(
            'operation', 'UPDATE',
            'old_data', row_to_json(OLD),
            'new_data', row_to_json(NEW)
        )::text);
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        PERFORM pg_notify('order_changes', json_build_object(
            'operation', 'DELETE',
            'data', row_to_json(OLD)
        )::text);
        RETURN OLD;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- trigger to notify any changes to the orders table
CREATE TRIGGER notify_any_orders_changes_trigger
    AFTER INSERT OR UPDATE OR DELETE ON orders
    FOR EACH ROW
    EXECUTE FUNCTION notify_any_orders_changes();


CREATE OR REPLACE FUNCTION update_updated_at_columns()
RETURNS TRIGGER AS $$
BEGIN 
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


CREATE TRIGGER update_updated_at_trigger
    BEFORE UPDATE ON orders
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_columns();

