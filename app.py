from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash, send_file
import mysql.connector
from mysql.connector import Error
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
import pandas as pd
import os

print("App is starting...")

app = Flask(__name__)
app.secret_key = "change-this-secret-key-in-production"

@app.route('/')
def home():
    return "Supermarket SaaS is running successfully!"

# File upload configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'xlsx', 'xls'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Create uploads directory if it doesn't exist
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# -----------------------
# DB CONNECTION
# -----------------------
def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host='localhost',
            user='root',  # Change this to your MySQL username
            password='',  # Change this to your MySQL password
            database='supermarket_saas'
        )
        return conn
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None

# -----------------------
# LOGIN REQUIRED DECORATORS
# -----------------------
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login first", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Admin access only", "danger")
            return redirect(url_for("user_dashboard"))
        return f(*args, **kwargs)
    return decorated

# -----------------------
# DATABASE INITIALIZATION
# -----------------------
def init_database():
    conn = get_db_connection()
    if not conn:
        print("Failed to connect to database")
        return
    
    cur = conn.cursor()

    # Create database if not exists
    try:
        cur.execute("CREATE DATABASE IF NOT EXISTS supermarket_saas")
        cur.execute("USE supermarket_saas")
    except Error as e:
        print(f"Error creating database: {e}")

    # Users table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(255) UNIQUE,
            password VARCHAR(255),
            role VARCHAR(50),
            store_id INT,
            full_name VARCHAR(255),
            email VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (store_id) REFERENCES stores (id)
        )
    """)

    # Products table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) UNIQUE,
            price DECIMAL(10, 2),
            gst DECIMAL(5, 2),
            stock INT,
            product_code VARCHAR(100) UNIQUE,
            cost_price DECIMAL(10, 2) DEFAULT 0
        )
    """)

    # Stores table (must be created before users due to foreign key)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS stores (
            id INT AUTO_INCREMENT PRIMARY KEY,
            store_name VARCHAR(255),
            location VARCHAR(255),
            phone VARCHAR(50),
            active TINYINT DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Bills table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bills_new (
            id INT AUTO_INCREMENT PRIMARY KEY,
            bill_number VARCHAR(100) UNIQUE,
            total DECIMAL(10, 2),
            discount DECIMAL(10, 2),
            payment_mode VARCHAR(50),
            bill_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by INT
        )
    """)

    # Bill items table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bill_items (
            id INT AUTO_INCREMENT PRIMARY KEY,
            bill_id INT,
            product_name VARCHAR(255),
            quantity INT,
            price DECIMAL(10, 2),
            gst DECIMAL(5, 2),
            item_total DECIMAL(10, 2)
        )
    """)

    # Purchases table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS purchases (
            id INT AUTO_INCREMENT PRIMARY KEY,
            product_id INT,
            quantity INT,
            cost_price DECIMAL(10, 2),
            supplier VARCHAR(255),
            created_by INT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id),
            FOREIGN KEY (created_by) REFERENCES users(id)
        )
    """)

    # Stock movements table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS stock_movements (
            id INT AUTO_INCREMENT PRIMARY KEY,
            product_id INT,
            change_qty INT,
            movement_type VARCHAR(50),
            reference_id INT,
            created_by INT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id),
            FOREIGN KEY (created_by) REFERENCES users(id)
        )
    """)

    # Activity logs table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS activity_logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT,
            action VARCHAR(255),
            details TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Default admin
    cur.execute("SELECT * FROM users WHERE username='admin'")
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
            ("admin", generate_password_hash("admin123"), "admin")
        )
        print("✓ Default admin created (username: admin, password: admin123)")

    # Sample products for demo
    cur.execute("SELECT COUNT(*) FROM products")
    result = cur.fetchone()
    if result[0] == 0:
        sample_products = [
            ("Rice 1kg", 60.0, 5.0, 100, "RICE100"),
            ("Milk 500ml", 25.0, 5.0, 50, "MILK500"),
            ("Sugar 1kg", 45.0, 5.0, 75, "SUGAR100"),
            ("Oil 1L", 120.0, 5.0, 30, "OIL100"),
            ("Bread", 30.0, 5.0, 40, "BREAD001"),
            ("Eggs 12pcs", 80.0, 5.0, 25, "EGGS012")
        ]
        for product in sample_products:
            cur.execute(
                "INSERT INTO products (name, price, gst, stock, product_code) VALUES (%s, %s, %s, %s, %s)",
                product
            )
        print("✓ Sample products created for demo")

    conn.commit()
    conn.close()
    print("✓ Database initialized!")

# -----------------------
# ACTIVITY LOGGING
# -----------------------
def log_activity(user_id, action, details=""):
    try:
        conn = get_db_connection()
        if not conn:
            return
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO activity_logs (user_id, action, details) VALUES (%s, %s, %s)",
            (user_id, action, details)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error logging activity: {e}")

# -----------------------
# LOGIN / LOGOUT
# -----------------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Please enter both username and password", "danger")
            return render_template("login.html")

        conn = get_db_connection()
        if not conn:
            flash("Database connection error", "danger")
            return render_template("login.html")
        
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM users WHERE username=%s", (username,))
        user = cur.fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            log_activity(user["id"], "Login", f"User {username} logged in")
            flash(f"Welcome back, {username}!", "success")
            
            if user["role"] == "admin":
                return redirect(url_for("admin_dashboard"))
            return redirect(url_for("user_dashboard"))

        flash("Invalid username or password", "danger")

    return render_template("login.html")

@app.route("/logout")
def logout():
    user_id = session.get("user_id")
    username = session.get("username", "User")
    if user_id:
        log_activity(user_id, "Logout", f"User {username} logged out")
    session.clear()
    flash(f"Goodbye, {username}!", "info")
    return redirect(url_for("login"))

# -----------------------
# DASHBOARDS
# -----------------------
@app.route("/admin")
@login_required
@admin_required
def admin_dashboard():
    conn = get_db_connection()
    if not conn:
        flash("Database connection error", "danger")
        return redirect(url_for("login"))
    
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) FROM products")
    total_products = cur.fetchone()[0] or 0

    cur.execute("SELECT COUNT(*) FROM bills_new")
    total_bills = cur.fetchone()[0] or 0

    cur.execute("SELECT COALESCE(SUM(total), 0) FROM bills_new")
    total_sales = cur.fetchone()[0] or 0

    cur.execute("SELECT COUNT(*) FROM stores WHERE active = 1")
    total_stores = cur.fetchone()[0] or 0

    conn.close()
    
    stats = {
        "total_products": total_products,
        "total_bills": total_bills,
        "total_sales": total_sales,
        "total_stores": total_stores
    }
    return render_template("admin_dashboard.html", stats=stats)

@app.route("/user")
@login_required
def user_dashboard():
    conn = get_db_connection()
    if not conn:
        flash("Database connection error", "danger")
        return redirect(url_for("login"))
    
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM products")
    total_products = cur.fetchone()[0] or 0

    cur.execute("SELECT COUNT(*) FROM bills_new WHERE created_by = %s", (session["user_id"],))
    user_bills = cur.fetchone()[0] or 0

    cur.execute("SELECT COALESCE(SUM(total), 0) FROM bills_new WHERE created_by = %s", (session["user_id"],))
    user_sales = cur.fetchone()[0] or 0

    cur.execute("SELECT COUNT(*) FROM products WHERE stock < 10")
    low_stock_items = cur.fetchone()[0] or 0

    conn.close()

    stats = {
        "total_products": total_products,
        "user_bills": user_bills,
        "user_sales": user_sales,
        "low_stock_items": low_stock_items
    }
    return render_template("user_dashboard.html", stats=stats)

@app.route("/dashboard")
@login_required
def dashboard():
    """Redirect to appropriate dashboard based on role"""
    if session.get("role") == "admin":
        return redirect(url_for("admin_dashboard"))
    return redirect(url_for("user_dashboard"))

# -----------------------
# PRODUCTS
# -----------------------
@app.route("/inventory")
@login_required
def inventory():
    conn = get_db_connection()
    if not conn:
        flash("Database connection error", "danger")
        return redirect(url_for("dashboard"))
    
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM products ORDER BY name")
    products = cur.fetchall()
    conn.close()
    return render_template("inventory.html", products=products)

@app.route("/add_product", methods=["GET", "POST"])
@login_required
def add_product():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        price = request.form.get("price", "")
        gst = request.form.get("gst", "")
        stock = request.form.get("stock", "")
        product_code = request.form.get("product_code", "").strip().upper()

        if not name or not product_code:
            flash("Product name and product code are required", "danger")
            return render_template("add_product.html")

        try:
            price = float(price)
            gst = float(gst)
            stock = int(stock)
        except ValueError:
            flash("Invalid price, GST, or stock value", "danger")
            return render_template("add_product.html")

        conn = get_db_connection()
        if not conn:
            flash("Database connection error", "danger")
            return render_template("add_product.html")
        
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO products (name, price, gst, stock, product_code) VALUES (%s, %s, %s, %s, %s)",
                        (name, price, gst, stock, product_code))
            conn.commit()
            log_activity(session["user_id"], "Add Product", f"Added product '{name}' with code '{product_code}'")
            flash(f"Product '{name}' added successfully!", "success")
            return redirect(url_for("inventory"))
        except Error as e:
            if "Duplicate entry" in str(e):
                if "name" in str(e):
                    flash("A product with this name already exists", "danger")
                elif "product_code" in str(e):
                    flash("A product with this code already exists", "danger")
                else:
                    flash("Duplicate entry error", "danger")
            else:
                flash(f"Database error occurred: {str(e)}", "danger")
        finally:
            conn.close()
            
    return render_template("add_product.html")

@app.route("/bulk_import", methods=["GET", "POST"])
@login_required
def bulk_import():
    if request.method == "POST":
        if 'file' not in request.files:
            flash('No file selected', 'danger')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('No file selected', 'danger')
            return redirect(request.url)
        
        if not allowed_file(file.filename):
            flash('Invalid file type. Please upload an Excel file (.xlsx or .xls)', 'danger')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            try:
                # Read Excel file
                df = pd.read_excel(filepath)
                
                # Validate required columns
                required_columns = ['name', 'price', 'gst', 'stock']
                optional_columns = ['product_code']
                
                # Check if all required columns are present
                if not all(col in df.columns for col in required_columns):
                    flash('Excel file must contain columns: name, price, gst, stock', 'danger')
                    os.remove(filepath)
                    return redirect(request.url)
                
                # Process each row
                conn = get_db_connection()
                if not conn:
                    flash("Database connection error", "danger")
                    os.remove(filepath)
                    return redirect(request.url)
                
                cur = conn.cursor()
                imported_count = 0
                errors = []
                
                for index, row in df.iterrows():
                    try:
                        name = str(row['name']).strip()
                        price = float(row['price'])
                        gst = float(row['gst'])
                        stock = int(row['stock'])
                        
                        # Handle optional product_code
                        product_code = None
                        if 'product_code' in df.columns and pd.notna(row.get('product_code')):
                            product_code = str(row['product_code']).strip().upper()
                        
                        if not name:
                            errors.append(f"Row {index+2}: Product name cannot be empty")
                            continue
                        
                        if price < 0 or gst < 0 or stock < 0:
                            errors.append(f"Row {index+2}: Price, GST, and stock must be non-negative")
                            continue
                        
                        # Insert with or without product_code
                        if product_code:
                            cur.execute("INSERT INTO products (name, price, gst, stock, product_code) VALUES (%s, %s, %s, %s, %s)",
                                        (name, price, gst, stock, product_code))
                        else:
                            cur.execute("INSERT INTO products (name, price, gst, stock) VALUES (%s, %s, %s, %s)",
                                        (name, price, gst, stock))
                        imported_count += 1
                        
                    except (ValueError, TypeError) as e:
                        errors.append(f"Row {index+2}: Invalid data - {str(e)}")
                    except Error as e:
                        if "Duplicate entry" in str(e):
                            if "name" in str(e):
                                errors.append(f"Row {index+2}: Product '{name}' already exists")
                            elif "product_code" in str(e):
                                errors.append(f"Row {index+2}: Product code '{product_code}' already exists")
                            else:
                                errors.append(f"Row {index+2}: Duplicate entry error")
                        else:
                            errors.append(f"Row {index+2}: Database error - {str(e)}")
                
                conn.commit()
                conn.close()
                
                # Log the bulk import
                log_activity(session["user_id"], "Bulk Import", f"Imported {imported_count} products from Excel file")
                
                # Clean up uploaded file
                os.remove(filepath)
                
                if imported_count > 0:
                    flash(f"Successfully imported {imported_count} products!", "success")
                if errors:
                    flash(f"Import completed with {len(errors)} errors:<br>" + "<br>".join(errors[:5]), "warning")
                
                return redirect(url_for("inventory"))
                
            except Exception as e:
                flash(f"Error processing file: {str(e)}", "danger")
                if os.path.exists(filepath):
                    os.remove(filepath)
                return redirect(request.url)
    
    return render_template("bulk_import.html")

@app.route("/download_template")
@login_required
def download_template():
    # Create a sample Excel template
    import io
    
    # Create sample data with all columns including product_code
    sample_data = {
        'name': ['Rice 1kg', 'Milk 500ml', 'Sugar 1kg', 'Oil 1L'],
        'price': [60.0, 25.0, 45.0, 120.0],
        'gst': [5.0, 5.0, 5.0, 5.0],
        'stock': [100, 50, 75, 30],
        'product_code': ['RICE100', 'MILK500', 'SUGAR100', 'OIL100']
    }
    
    df = pd.DataFrame(sample_data)
    
    # Create Excel file in memory
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Products', index=False)
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='product_template.xlsx'
    )

# -----------------------
# PURCHASE ENTRY MODULE
# -----------------------
@app.route("/add_purchase", methods=["GET", "POST"])
@login_required
@admin_required
def add_purchase():
    if request.method == "POST":
        product_id = request.form.get("product_id")
        quantity = request.form.get("quantity")
        cost_price = request.form.get("cost_price")
        supplier = request.form.get("supplier", "").strip()

        if not product_id or not quantity or not cost_price:
            flash("All fields are required", "danger")
            return redirect(url_for("add_purchase"))

        try:
            quantity = int(quantity)
            cost_price = float(cost_price)
        except ValueError:
            flash("Invalid quantity or cost price", "danger")
            return redirect(url_for("add_purchase"))

        if quantity <= 0 or cost_price < 0:
            flash("Quantity must be positive and cost price cannot be negative", "danger")
            return redirect(url_for("add_purchase"))

        conn = get_db_connection()
        if not conn:
            flash("Database connection error", "danger")
            return redirect(url_for("add_purchase"))
        
        cur = conn.cursor()

        # Check for duplicate purchase within last 30 seconds
        cur.execute("""
            SELECT id FROM purchases 
            WHERE product_id = %s AND quantity = %s AND cost_price = %s AND supplier = %s AND created_by = %s
            AND created_at > DATE_SUB(NOW(), INTERVAL 30 SECOND)
        """, (product_id, quantity, cost_price, supplier, session["user_id"]))
        
        if cur.fetchone():
            flash("Duplicate purchase detected. Please wait before submitting again.", "warning")
            conn.close()
            return redirect(url_for("add_purchase"))

        try:
            # Insert purchase record
            cur.execute("""
                INSERT INTO purchases (product_id, quantity, cost_price, supplier, created_by)
                VALUES (%s, %s, %s, %s, %s)
            """, (product_id, quantity, cost_price, supplier, session["user_id"]))

            purchase_id = cur.lastrowid

            # Update product stock and cost_price
            cur.execute("""
                UPDATE products 
                SET stock = stock + %s, cost_price = %s 
                WHERE id = %s
            """, (quantity, cost_price, product_id))

            # Insert stock movement
            cur.execute("""
                INSERT INTO stock_movements (product_id, change_qty, movement_type, reference_id, created_by)
                VALUES (%s, %s, 'PURCHASE', %s, %s)
            """, (product_id, quantity, purchase_id, session["user_id"]))

            conn.commit()
            log_activity(session["user_id"], "Add Purchase", f"Added purchase for product ID {product_id}, quantity {quantity}")
            flash("Purchase added successfully!", "success")
            return redirect(url_for("inventory"))

        except Exception as e:
            conn.rollback()
            flash(f"Error adding purchase: {str(e)}", "danger")
        finally:
            conn.close()

    # Get products for dropdown
    conn = get_db_connection()
    if not conn:
        flash("Database connection error", "danger")
        return redirect(url_for("dashboard"))
    
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, name FROM products ORDER BY name")
    products = cur.fetchall()
    conn.close()

    return render_template("add_purchase.html", products=products)

# -----------------------
# STOCK ADJUSTMENT MODULE
# -----------------------
@app.route("/stock_adjustment", methods=["GET", "POST"])
@login_required
@admin_required
def stock_adjustment():
    if request.method == "POST":
        product_id = request.form.get("product_id")
        adjustment_type = request.form.get("adjustment_type")  # DAMAGE or EXPIRED
        quantity = request.form.get("quantity")
        reason = request.form.get("reason", "").strip()

        if not product_id or not adjustment_type or not quantity:
            flash("All fields are required", "danger")
            return redirect(url_for("stock_adjustment"))

        try:
            quantity = int(quantity)
        except ValueError:
            flash("Invalid quantity", "danger")
            return redirect(url_for("stock_adjustment"))

        if quantity <= 0:
            flash("Quantity must be positive", "danger")
            return redirect(url_for("stock_adjustment"))

        if adjustment_type not in ['DAMAGE', 'EXPIRED']:
            flash("Invalid adjustment type", "danger")
            return redirect(url_for("stock_adjustment"))

        conn = get_db_connection()
        if not conn:
            flash("Database connection error", "danger")
            return redirect(url_for("stock_adjustment"))
        
        cur = conn.cursor(dictionary=True)

        try:
            # Check current stock
            cur.execute("SELECT stock FROM products WHERE id = %s", (product_id,))
            product = cur.fetchone()

            if not product or product['stock'] < quantity:
                flash("Insufficient stock for adjustment", "danger")
                conn.close()
                return redirect(url_for("stock_adjustment"))

            # Reduce product stock
            cur.execute("""
                UPDATE products 
                SET stock = stock - %s 
                WHERE id = %s
            """, (quantity, product_id))

            # Insert stock movement (negative quantity)
            cur.execute("""
                INSERT INTO stock_movements (product_id, change_qty, movement_type, created_by)
                VALUES (%s, %s, %s, %s)
            """, (product_id, -quantity, adjustment_type, session["user_id"]))

            conn.commit()
            log_activity(session["user_id"], f"Stock {adjustment_type}", f"Adjusted {quantity} units of product ID {product_id} as {adjustment_type}")
            flash(f"Stock adjustment ({adjustment_type}) completed successfully!", "success")
            return redirect(url_for("inventory"))

        except Exception as e:
            conn.rollback()
            flash(f"Error processing adjustment: {str(e)}", "danger")
        finally:
            conn.close()

    # Get products for dropdown
    conn = get_db_connection()
    if not conn:
        flash("Database connection error", "danger")
        return redirect(url_for("dashboard"))
    
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, name, stock FROM products WHERE stock > 0 ORDER BY name")
    products = cur.fetchall()
    conn.close()

    return render_template("stock_adjustment.html", products=products)

# -----------------------
# STOCK MOVEMENT HISTORY
# -----------------------
@app.route("/stock_history/<int:product_id>")
@login_required
@admin_required
def stock_history(product_id):
    conn = get_db_connection()
    if not conn:
        flash("Database connection error", "danger")
        return redirect(url_for("inventory"))
    
    cur = conn.cursor(dictionary=True)

    # Get product details
    cur.execute("SELECT * FROM products WHERE id = %s", (product_id,))
    product = cur.fetchone()

    if not product:
        flash("Product not found", "danger")
        conn.close()
        return redirect(url_for("inventory"))

    # Get stock movements
    cur.execute("""
        SELECT sm.*, u.username, 
               CASE 
                   WHEN sm.movement_type = 'PURCHASE' THEN 'Purchase'
                   WHEN sm.movement_type = 'SALE' THEN 'Sale'
                   WHEN sm.movement_type = 'DAMAGE' THEN 'Damage'
                   WHEN sm.movement_type = 'EXPIRED' THEN 'Expired'
                   ELSE sm.movement_type
               END as movement_description
        FROM stock_movements sm
        JOIN users u ON sm.created_by = u.id
        WHERE sm.product_id = %s
        ORDER BY sm.created_at DESC
    """, (product_id,))
    
    movements = cur.fetchall()
    conn.close()

    return render_template("stock_history.html", product=product, movements=movements)

@app.route("/edit_product/<int:id>", methods=["GET", "POST"])
@login_required
@admin_required
def edit_product(id):
    conn = get_db_connection()
    if not conn:
        flash("Database connection error", "danger")
        return redirect(url_for("inventory"))
    
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM products WHERE id=%s", (id,))
    product = cur.fetchone()

    if not product:
        flash("Product not found", "danger")
        conn.close()
        return redirect(url_for("inventory"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        price = request.form.get("price", "")
        gst = request.form.get("gst", "")
        stock = request.form.get("stock", "")
        
        try:
            price = float(price)
            gst = float(gst)
            stock = int(stock)
            
            cur.execute("UPDATE products SET name=%s, price=%s, gst=%s, stock=%s WHERE id=%s",
                        (name, price, gst, stock, id))
            conn.commit()
            flash(f"Product '{name}' updated successfully!", "success")
            return redirect(url_for("inventory"))
        except ValueError:
            flash("Invalid price, GST, or stock value", "danger")
        except Error as e:
            if "Duplicate entry" in str(e):
                flash("A product with this name already exists", "danger")
            else:
                flash(f"Database error: {str(e)}", "danger")
        finally:
            conn.close()

    conn.close()
    return render_template("edit_product.html", product=product)

@app.route("/delete_product/<int:id>")
@login_required
@admin_required
def delete_product(id):
    conn = get_db_connection()
    if not conn:
        flash("Database connection error", "danger")
        return redirect(url_for("inventory"))
    
    cur = conn.cursor()
    cur.execute("DELETE FROM products WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    flash("Product deleted successfully", "success")
    return redirect(url_for("inventory"))

# -----------------------
# LOW STOCK & ADD STOCK
# -----------------------
@app.route("/low_stock")
@login_required
def low_stock():
    threshold = request.args.get('threshold', 10, type=int)
    
    conn = get_db_connection()
    if not conn:
        flash("Database connection error", "danger")
        return redirect(url_for("dashboard"))
    
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, name, stock, price FROM products WHERE stock < %s ORDER BY stock ASC", (threshold,))
    low_stock_products = cur.fetchall()
    conn.close()
    
    return render_template("low_stock.html", low_stock_products=low_stock_products, threshold=threshold)

@app.route("/add_stock/<int:product_id>", methods=["GET", "POST"])
@login_required
@admin_required
def add_stock(product_id):
    conn = get_db_connection()
    if not conn:
        flash("Database connection error", "danger")
        return redirect(url_for("low_stock"))
    
    cur = conn.cursor(dictionary=True)
    
    if request.method == "POST":
        try:
            quantity = int(request.form.get("quantity", 0))
            
            if quantity <= 0:
                flash("Quantity must be positive", "danger")
            else:
                cur.execute("UPDATE products SET stock = stock + %s WHERE id = %s", (quantity, product_id))
                conn.commit()
                flash(f"Added {quantity} units to stock successfully!", "success")
                return redirect(url_for("low_stock"))
        except ValueError:
            flash("Invalid quantity", "danger")
        finally:
            conn.close()
    
    cur.execute("SELECT id, name, stock, price FROM products WHERE id = %s", (product_id,))
    product = cur.fetchone()
    conn.close()
    
    if not product:
        flash("Product not found", "danger")
        return redirect(url_for("low_stock"))
    
    return render_template("add_stock.html", product=product)

# -----------------------
# STORES
# -----------------------
@app.route("/stores")
@login_required
def stores():
    conn = get_db_connection()
    if not conn:
        flash("Database connection error", "danger")
        return redirect(url_for("dashboard"))
    
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM stores ORDER BY created_at DESC")
    stores = cur.fetchall()
    conn.close()
    return render_template("stores.html", stores=stores)

@app.route("/add_store", methods=["GET", "POST"])
@login_required
@admin_required
def add_store():
    if request.method == "POST":
        store_name = request.form.get("store_name", "").strip()
        location = request.form.get("location", "").strip()
        phone = request.form.get("phone", "").strip()
        
        if not store_name:
            flash("Store name is required", "danger")
            return render_template("add_store.html")
        
        conn = get_db_connection()
        if not conn:
            flash("Database connection error", "danger")
            return render_template("add_store.html")
        
        cur = conn.cursor()
        cur.execute("INSERT INTO stores (store_name, location, phone) VALUES (%s, %s, %s)",
                    (store_name, location, phone))
        conn.commit()
        conn.close()
        flash(f"Store '{store_name}' added successfully!", "success")
        return redirect(url_for("stores"))
        
    return render_template("add_store.html")

# -----------------------
# USERS
# -----------------------
@app.route("/users")
@login_required
@admin_required
def users():
    conn = get_db_connection()
    if not conn:
        flash("Database connection error", "danger")
        return redirect(url_for("dashboard"))
    
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM users ORDER BY id DESC")
    users = cur.fetchall()
    conn.close()
    return render_template("users.html", users=users)

@app.route("/add_user", methods=["GET", "POST"])
@login_required
@admin_required
def add_user():
    # Fetch stores for the dropdown
    conn = get_db_connection()
    if not conn:
        flash("Database connection error", "danger")
        return redirect(url_for("users"))
    
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, store_name FROM stores WHERE active = 1 ORDER BY store_name")
    stores = cur.fetchall()
    conn.close()
    
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "")
        store_id = request.form.get("store_id", "").strip()
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip()
        
        if not username or not password or not role:
            flash("Username, password, and role are required", "danger")
            return render_template("add_user.html", stores=stores)
        
        # Validate store assignment for non-company admins
        if role in ['store_admin', 'store_user'] and not store_id:
            flash("Store assignment is required for store admins and users", "danger")
            return render_template("add_user.html", stores=stores)
        
        # Convert store_id to None for company admins
        if role == 'company_admin':
            store_id = None
        elif store_id:
            store_id = int(store_id)
        
        conn = get_db_connection()
        if not conn:
            flash("Database connection error", "danger")
            return render_template("add_user.html", stores=stores)
        
        cur = conn.cursor()
        try:
            hashed_password = generate_password_hash(password)
            cur.execute("""
                INSERT INTO users (username, password, role, store_id, full_name, email) 
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (username, hashed_password, role, store_id, full_name, email))
            conn.commit()
            log_activity(session["user_id"], "Add User", f"Added user '{username}' with role '{role}'")
            flash(f"User '{username}' added successfully!", "success")
            return redirect(url_for("users"))
        except Error as e:
            if "Duplicate entry" in str(e):
                flash("Username already exists", "danger")
            else:
                flash(f"Database error: {str(e)}", "danger")
        finally:
            conn.close()
            
    return render_template("add_user.html", stores=stores)

# -----------------------
# ACTIVITY LOG
# -----------------------
@app.route("/activity_log")
@login_required
@admin_required
def activity_log():
    conn = get_db_connection()
    if not conn:
        flash("Database connection error", "danger")
        return redirect(url_for("dashboard"))
    
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT al.*, u.username, s.store_name 
        FROM activity_logs al 
        JOIN users u ON al.user_id = u.id 
        LEFT JOIN stores s ON u.store_id = s.id 
        ORDER BY al.timestamp DESC 
        LIMIT 100
    """)
    logs = cur.fetchall()
    conn.close()
    return render_template("activity_log.html", logs=logs)

# -----------------------
# BILLING
# -----------------------
@app.route("/billing")
@login_required
def billing():
    conn = get_db_connection()
    if not conn:
        flash("Database connection error", "danger")
        return redirect(url_for("dashboard"))
    
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM products WHERE stock > 0 ORDER BY name")
    products = cur.fetchall()
    conn.close()
    return render_template("billing.html", products=products)

@app.route("/get_product_by_code", methods=["POST"])
@login_required
def get_product_by_code():
    data = request.json
    product_code = data.get("product_code", "").strip().upper()
    
    if not product_code:
        return jsonify({"error": "Product code is required"}), 400
    
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection error"}), 500
    
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, name, price, gst, stock FROM products WHERE product_code = %s AND stock > 0", (product_code,))
    product = cur.fetchone()
    conn.close()
    
    if product:
        return jsonify({
            "id": product["id"],
            "name": product["name"],
            "price": float(product["price"]),
            "gst": float(product["gst"]),
            "stock": product["stock"]
        })
    else:
        return jsonify({"error": "Product not found or out of stock"}), 404

@app.route("/process_checkout", methods=["POST"])
@login_required
def process_checkout():
    data = request.json
    cart = data.get("cart", [])
    discount = float(data.get("discount", 0))
    payment_mode = data.get("payment_mode", "Cash")

    if not cart:
        return jsonify({"success": False, "message": "Cart is empty"}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"success": False, "message": "Database connection error"}), 500
    
    cur = conn.cursor(dictionary=True)

    try:
        subtotal = 0
        gst_total = 0

        for item in cart:
            item_subtotal = item["price"] * item["qty"]
            item_gst = item_subtotal * (item["gst"] / 100)
            subtotal += item_subtotal
            gst_total += item_gst

        total = subtotal + gst_total - discount
        bill_no = f"BILL{datetime.now().strftime('%Y%m%d%H%M%S')}"

        cur.execute("""
            INSERT INTO bills_new (bill_number, total, discount, payment_mode, bill_date, created_by)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (bill_no, total, discount, payment_mode, datetime.now(), session["user_id"]))

        bill_id = cur.lastrowid

        for item in cart:
            # Check stock availability
            cur.execute("SELECT stock FROM products WHERE id=%s", (item["id"],))
            product = cur.fetchone()
            
            if not product or product['stock'] < item["qty"]:
                raise ValueError(f"Insufficient stock for {item['name']}")
            
            item_total = (item["price"] * item["qty"]) + ((item["price"] * item["qty"]) * item["gst"] / 100)
            cur.execute("""
                INSERT INTO bill_items (bill_id, product_name, quantity, price, gst, item_total)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (bill_id, item["name"], item["qty"], item["price"], item["gst"], item_total))

            cur.execute("UPDATE products SET stock = stock - %s WHERE id=%s", (item["qty"], item["id"]))

            # Log stock movement for sale (negative quantity)
            cur.execute("""
                INSERT INTO stock_movements (product_id, change_qty, movement_type, reference_id, created_by)
                VALUES (%s, %s, 'SALE', %s, %s)
            """, (item["id"], -item["qty"], bill_id, session["user_id"]))

        conn.commit()
        log_activity(session["user_id"], "Create Bill", f"Created bill {bill_no} with total ₹{round(total, 2)}")
        return jsonify({"success": True, "bill_number": bill_no, "total": round(total, 2)})
    
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()

@app.route("/view_bill/<int:bill_id>")
@login_required
def view_bill(bill_id):
    conn = get_db_connection()
    if not conn:
        flash("Database connection error", "danger")
        return redirect(url_for("reports"))
    
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM bills_new WHERE id=%s", (bill_id,))
    bill = cur.fetchone()
    
    if not bill:
        flash("Bill not found", "danger")
        conn.close()
        return redirect(url_for("reports"))
    
    cur.execute("SELECT * FROM bill_items WHERE bill_id=%s", (bill_id,))
    items = cur.fetchall()
    conn.close()
    return render_template("view_bill.html", bill=bill, items=items)

@app.route("/print_bill_a4/<int:bill_id>")
@login_required
def print_bill_a4(bill_id):
    conn = get_db_connection()
    if not conn:
        flash("Database connection error", "danger")
        return redirect(url_for("reports"))
    
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM bills_new WHERE id=%s", (bill_id,))
    bill = cur.fetchone()
    
    if not bill:
        flash("Bill not found", "danger")
        conn.close()
        return redirect(url_for("reports"))
    
    cur.execute("SELECT * FROM bill_items WHERE bill_id=%s", (bill_id,))
    items = cur.fetchall()
    
    # Calculate subtotal and GST
    subtotal = 0
    total_gst = 0
    for item in items:
        item_price = float(item['price']) * item['quantity']
        item_gst = item_price * (float(item['gst']) / 100)
        subtotal += item_price
        total_gst += item_gst
    
    conn.close()
    return render_template("print_bill_a4.html", bill=bill, items=items, subtotal=subtotal, total_gst=total_gst)

@app.route("/print_bill_thermal/<int:bill_id>")
@login_required
def print_bill_thermal(bill_id):
    conn = get_db_connection()
    if not conn:
        flash("Database connection error", "danger")
        return redirect(url_for("reports"))
    
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM bills_new WHERE id=%s", (bill_id,))
    bill = cur.fetchone()
    
    if not bill:
        flash("Bill not found", "danger")
        conn.close()
        return redirect(url_for("reports"))
    
    cur.execute("SELECT * FROM bill_items WHERE bill_id=%s", (bill_id,))
    items = cur.fetchall()
    
    # Calculate subtotal and GST
    subtotal = 0
    total_gst = 0
    for item in items:
        item_price = float(item['price']) * item['quantity']
        item_gst = item_price * (float(item['gst']) / 100)
        subtotal += item_price
        total_gst += item_gst
    
    conn.close()
    return render_template("print_bill_thermal.html", bill=bill, items=items, subtotal=subtotal, total_gst=total_gst)

# -----------------------
# REPORTS
# -----------------------
@app.route("/reports")
@login_required
def reports():
    report_type = request.args.get('type', 'all')
    
    # Validate report type
    valid_types = ['daily', 'weekly', 'monthly', 'all']
    if report_type not in valid_types:
        report_type = 'all'
    
    conn = get_db_connection()
    if not conn:
        flash("Database connection error", "danger")
        return redirect(url_for("dashboard"))
    
    cur = conn.cursor(dictionary=True)
    
    # Build query based on report type
    if report_type == 'daily':
        date_filter = "DATE(bill_date) = CURDATE()"
    elif report_type == 'weekly':
        date_filter = "DATE(bill_date) >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)"
    elif report_type == 'monthly':
        date_filter = "DATE_FORMAT(bill_date, '%Y-%m') = DATE_FORMAT(CURDATE(), '%Y-%m')"
    else:  # all
        date_filter = "1=1"
    
    # Get bills with filter
    query = f"""
        SELECT bill_number, bill_date, total, payment_mode, id
        FROM bills_new
        WHERE {date_filter}
        ORDER BY bill_date DESC
    """
    cur.execute(query)
    bills = cur.fetchall()
    
    # Get statistics
    stats_query = f"""
        SELECT COUNT(*), COALESCE(SUM(total), 0), COALESCE(SUM(discount), 0)
        FROM bills_new
        WHERE {date_filter}
    """
    cur.execute(stats_query)
    stats_row = cur.fetchone()
    stats = (stats_row['COUNT(*)'], float(stats_row['COALESCE(SUM(total), 0)']), float(stats_row['COALESCE(SUM(discount), 0)']))
    
    # Get purchase statistics
    if report_type == 'daily':
        purchase_date_filter = "DATE(p.created_at) = CURDATE()"
    elif report_type == 'weekly':
        purchase_date_filter = "DATE(p.created_at) >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)"
    elif report_type == 'monthly':
        purchase_date_filter = "DATE_FORMAT(p.created_at, '%Y-%m') = DATE_FORMAT(CURDATE(), '%Y-%m')"
    else:  # all
        purchase_date_filter = "1=1"
    
    purchase_query = f"""
        SELECT COALESCE(SUM(p.quantity * p.cost_price), 0) as total_purchases
        FROM purchases p
        WHERE {purchase_date_filter}
    """
    cur.execute(purchase_query)
    purchase_row = cur.fetchone()
    total_purchases = float(purchase_row['total_purchases']) if purchase_row else 0
    
    conn.close()
    return render_template("reports.html", bills=bills, stats=stats, total_purchases=total_purchases, report_type=report_type)

# -----------------------
# PRODUCT ANALYTICS
# -----------------------
@app.route("/product_analytics")
@login_required
@admin_required
def product_analytics():
    conn = get_db_connection()
    if not conn:
        flash("Database connection error", "danger")
        return redirect(url_for("dashboard"))
    
    cur = conn.cursor(dictionary=True)

    # Top selling products (based on quantity sold)
    cur.execute("""
        SELECT p.name, p.id, SUM(ABS(sm.change_qty)) as total_sold, 
               COUNT(DISTINCT sm.reference_id) as bills_count,
               p.stock as current_stock
        FROM stock_movements sm
        JOIN products p ON sm.product_id = p.id
        WHERE sm.movement_type = 'SALE'
        GROUP BY p.id, p.name, p.stock
        ORDER BY total_sold DESC
        LIMIT 10
    """)
    top_selling = cur.fetchall()

    # Low selling products (products with least sales or no sales)
    cur.execute("""
        SELECT p.name, p.id, COALESCE(SUM(ABS(sm.change_qty)), 0) as total_sold,
               COUNT(DISTINCT sm.reference_id) as bills_count,
               p.stock as current_stock
        FROM products p
        LEFT JOIN stock_movements sm ON p.id = sm.product_id AND sm.movement_type = 'SALE'
        GROUP BY p.id, p.name, p.stock
        ORDER BY total_sold ASC, p.stock DESC
        LIMIT 10
    """)
    low_selling = cur.fetchall()

    conn.close()
    return render_template("product_analytics.html", top_selling=top_selling, low_selling=low_selling)

# -----------------------
# MAIN
# -----------------------
if __name__ == "__main__":
    init_database()
    app.run(debug=True)
