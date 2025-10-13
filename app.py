from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import random, string
from decimal import Decimal

app = Flask(__name__)
app.secret_key = "secret"
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///shop.db'
db = SQLAlchemy(app)

# 🧩 توليد كود المنتج والباركود
def generate_product_code():
    letters = ''.join(random.choices(string.ascii_uppercase, k=2))
    numbers = ''.join(random.choices(string.digits, k=2))
    return f"PRD-{letters}{numbers}"

def generate_barcode():
    barcode = [random.randint(0, 9) for _ in range(12)]
    odd_sum = sum(barcode[-1::-2])
    even_sum = sum(barcode[-2::-2])
    check_digit = (10 - ((odd_sum * 3 + even_sum) % 10)) % 10
    barcode.append(check_digit)
    return ''.join(map(str, barcode))

# 🧩 الجداول
class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    price = db.Column(db.Float)
    quantity = db.Column(db.Integer)
    category = db.Column(db.String(50))
    description = db.Column(db.String(200))
    image = db.Column(db.String(200))
    barcode = db.Column(db.String(20))
    code = db.Column(db.String(20))
    created_at = db.Column(db.String(50))

class Receipt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    receipt_number = db.Column(db.String(50))
    date = db.Column(db.String(50))
    total = db.Column(db.Float)
    payment_method = db.Column(db.String(50))

class ReceiptItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    receipt_id = db.Column(db.Integer, db.ForeignKey('receipt.id'))
    product_id = db.Column(db.Integer)
    product_name = db.Column(db.String(100))
    quantity = db.Column(db.Integer)
    price = db.Column(db.Float)
    total = db.Column(db.Float)

class DailySale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(100))
    quantity = db.Column(db.Integer)
    price = db.Column(db.Float)
    total = db.Column(db.Float)
    sale_time = db.Column(db.String(20))

class CashTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float)
    note = db.Column(db.String(200))
    date = db.Column(db.DateTime, default=datetime.utcnow)

# 🧩 تهيئة قاعدة البيانات
with app.app_context():
    db.create_all()
    print("✅ Database tables created successfully")

# 🧩 الصفحة الرئيسية
@app.route('/')
def index():
    q = request.args.get('q', '')
    if q:
        products = Product.query.filter(Product.name.contains(q)).all()
    else:
        products = Product.query.all()
    return render_template('index.html', products=products, q=q)

# 🧩 API لجلب منتج
@app.route('/api/product/<int:pid>')
def get_product(pid):
    product = Product.query.get(pid)
    if not product:
        return jsonify({'error': 'Not found'}), 404
    return jsonify({
        'id': product.id,
        'name': product.name,
        'price': product.price,
        'quantity': product.quantity
    })

# 🧩 تنفيذ البيع
@app.route('/api/checkout', methods=['POST'])
def api_checkout():
    payload = request.get_json()
    if not payload:
        return jsonify({'error': 'Invalid payload'}), 400

    cart = payload.get('cart', [])
    payment_method = payload.get('payment_method', 'نقدي')
    if not cart:
        return jsonify({'error': 'cart empty'}), 400

    total_amount = sum(Decimal(str(item['price'])) * int(item['quantity']) for item in cart)
    receipt_number = f"RCP{datetime.now().strftime('%Y%m%d%H%M%S')}"
    receipt = Receipt(
        receipt_number=receipt_number,
        date=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        total=float(total_amount),
        payment_method=payment_method
    )
    db.session.add(receipt)
    db.session.flush()

    for it in cart:
        pid = it.get('id')
        name = it.get('name')
        qty = int(it.get('quantity'))
        price = Decimal(str(it.get('price')))
        total = price * qty

        db.session.add(ReceiptItem(
            receipt_id=receipt.id,
            product_id=pid,
            product_name=name,
            quantity=qty,
            price=float(price),
            total=float(total)
        ))

        product = Product.query.get(pid)
        if product:
            product.quantity = max(0, product.quantity - qty)

        db.session.add(DailySale(
            product_name=name,
            quantity=qty,
            price=float(price),
            total=float(total),
            sale_time=datetime.now().strftime('%H:%M:%S')
        ))

    # 💰 تحديث الخزنة تلقائيًا
    db.session.add(CashTransaction(
        amount=float(total_amount),
        note=f"مبيعات ({payment_method}) - فاتورة {receipt_number}"
    ))

    db.session.commit()
    return jsonify({'success': True, 'receipt_number': receipt_number, 'total': float(total_amount)})

# 🧩 حذف منتج
@app.route('/delete_product/<int:product_id>', methods=['POST'])
def delete_product(product_id):
    product = Product.query.get(product_id)
    if product:
        db.session.delete(product)
        db.session.commit()
        flash('✅ تم حذف المنتج بنجاح', 'success')
    else:
        flash('❌ المنتج غير موجود', 'danger')
    return redirect(url_for('index'))

# 🧩 صفحة التقارير
@app.route('/reports')
def reports():
    receipts = Receipt.query.order_by(Receipt.date.desc()).all()
    sales = DailySale.query.order_by(DailySale.id.desc()).limit(100).all()
    balance = sum(t.amount for t in CashTransaction.query.all())
    total_revenue = sum(r.total for r in receipts)
    return render_template('reports.html', receipts=receipts, sales=sales, balance=balance, total_revenue=total_revenue)

# 🧩 صفحة الخزنة
@app.route('/cash')
def cash():
    transactions = CashTransaction.query.order_by(CashTransaction.date.desc()).all()
    balance = sum(t.amount for t in transactions)
    return render_template('cash.html', transactions=transactions, balance=balance)

# 🧩 صفحة إضافة منتج
@app.route('/add_product', methods=['GET', 'POST'])
def add_product_web():
    if request.method == 'POST':
        name = request.form.get('product_name')
        price = request.form.get('product_price')
        quantity = request.form.get('product_quantity')
        category = request.form.get('product_category')
        desc = request.form.get('product_description')

        if not name or not price or not quantity:
            flash('❌ من فضلك أدخل بيانات صحيحة للمنتج', 'danger')
            return redirect(url_for('add_product_web'))

        new_product = Product(
            name=name,
            price=float(price),
            quantity=int(quantity),
            category=category,
            description=desc,
            image='',
            barcode=generate_barcode(),
            code=generate_product_code(),
            created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        )
        db.session.add(new_product)
        db.session.commit()
        flash('✅ تم إضافة المنتج بنجاح!', 'success')
        return redirect(url_for('index'))
    return render_template('add_product.html')

if __name__ == '__main__':
    app.run(debug=True)
