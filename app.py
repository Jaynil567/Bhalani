from flask import Flask, render_template, request, redirect, session
from datetime import timedelta
import gspread
import random
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import gspread
import psycopg2

order_id=1258

#------------ Flask App Setup --------------
app = Flask(__name__)
app.secret_key = "secret123"
app.permanent_session_lifetime = timedelta(days=30)

# ------------ Google Sheets Setup --------------
scope = ['https://spreadsheets.google.com/feeds',
'https://www.googleapis.com/auth/drive']

creds = ServiceAccountCredentials.from_json_keyfile_name('/etc/secrets/credentials.json', scope)
client = gspread.authorize(creds)
sheet = client.open("Bhalani Orders").sheet1

# ------------ Database Setup --------------
def get_db():
    conn = psycopg2.connect("postgresql://neondb_owner:npg_hHVzxn6yEP3X@ep-weathered-heart-a1bu4ids-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require")
    return conn

#------------ Routes --------------
# Home Route
@app.route("/")
def home():
    if "customer_number" in session:
        return redirect("/dashboard")
    
    return redirect("/login")


# Login Route
@app.route("/login", methods=["GET","POST"])
def login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        conn = get_db()
        cur = conn.cursor()

        cur.execute(
            "SELECT name,mobile,id FROM customers WHERE username=%s AND password=%s",
            (username,password)
        )

        user = cur.fetchone()

        cur.close()
        conn.close()

        if user:

            session.permanent = True

            
            session["company_name"] = user[0]
            session["customer_number"] = user[1]
            session["customer_id"] = user[2]

            return redirect("/dashboard")
        else:
            return render_template("login.html", error="Invalid User or Password")
        
    return render_template("login.html")

# Customer Dashboard Route
@app.route("/dashboard")
def dashboard():

    if "customer_id" not in session:
        return redirect("/login")

    records = sheet.get_all_records()
    records = records[::-1]  # reverse to show latest orders first

    orders = {}

    for row in records:

        if row["Status"] == "Removed":
            continue

        if str(row["Customer ID"]) == str(session["customer_id"]):

            order_id = row["OrderID"]

            if order_id not in orders:
                orders[order_id] = {
                    "timestamp": row["timestamp"],
                    "status": row["Status"],
                    "products": []
                }

            orders[order_id]["products"].append({
                "product": row["Product ID"],
                "qty": row["Quantity"]
            })

    return render_template(
        "customer/dashboard.html",
        company=session["company_name"],
        orders=orders
    )

def safe_append(sheet, data_dict):
    headers = sheet.row_values(1)
    row = []
    for header in headers:
        row.append(data_dict.get(header, ""))
    # find next empty row
    data = sheet.get_all_values()
    next_row = len(data) + 1
    sheet.insert_row(row, next_row)

@app.route("/order", methods=["GET","POST"])
def order():

    if "customer_id" not in session:
        return redirect("/login")

    if request.method == "POST":
        product_ids = request.form.getlist("product_id")
        qtys = request.form.getlist("qty")

        order_id = f"{order_id+1}"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for i in range(len(product_ids)):

            if product_ids[i] != "":
                order_data = {
                    "OrderID": order_id,
                    "Customer Number": session["customer_number"],
                    "Company Name": session["company_name"],
                    "Customer ID": session["customer_id"],
                    "Product ID": product_ids[i],
                    "Quantity": qtys[i],
                    "timestamp": timestamp,
                    "Status": "Order Placed"
                }   
                safe_append(sheet, order_data)

        return redirect("/dashboard")

    return render_template(
        "customer/order.html",
        company=session["company_name"]
    )

@app.route("/update_order", methods=["POST"])
def update_order():

    data = request.json
    order_id = data["order_id"]
    products = data["products"]
    qtys = data["qtys"]

    records = sheet.get_all_records()

    rows_to_delete = []

    # find order rows
    for i,row in enumerate(records,start=2):
        if str(row["OrderID"]) == str(order_id):
            rows_to_delete.append(i)

    # delete rows from bottom
    for r in sorted(rows_to_delete, reverse=True):
        sheet.delete_rows(r)

    from datetime import datetime
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    rows = []

    for i in range(len(products)):

        rows.append([
            timestamp,
            session["customer_id"],
            session["company_name"],
            session["customer_number"],
            order_id,
            products[i],
            qtys[i],
            "Order Placed"
        ])

    sheet.append_rows(rows)

    return {"status":"ok"}



# ------------------- Admin Routes (For Testing) -------------------
@app.route("/shop")
def shop_dashboard():

    records = sheet.get_all_records()

    orders = {}

    for row in records:

        oid = row["OrderID"]

        if oid not in orders:

            orders[oid] = {
                "timestamp": row["timestamp"],
                "company": row["Company Name"],
                "phone": row["Customer Number"],
                "status": row["Status"],
                "rider": row["Rider"] if "Rider" in row else "",
                "products":[]
            }

        orders[oid]["products"].append({
            "product":row["Product ID"],
            "qty":row["Quantity"]
        })

    orders = dict(list(orders.items())[::-1])

    return render_template("shop_dashboard.html", orders=orders)



@app.route("/shop/update_status", methods=["POST"])
def update_status():

    order_id = request.form["order_id"]
    status = request.form["status"]
    rider = request.form.get("rider","")

    records = sheet.get_all_records()

    for i,row in enumerate(records,start=2):

        if str(row["OrderID"]) == str(order_id):

            sheet.update(f"H{i}", [[status]])
            sheet.update(f"I{i}", [[rider]])

    return redirect("/shop")


# Logout Route
@app.route("/logout")
def logout():

    session.clear()
    return redirect("/login")


app.run(host="0.0.0.0", port=10000)







