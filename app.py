from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from decimal import Decimal
import random, string

app = Flask(__name__)
app.secret_key = "change_this_secret"
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///shop.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ------------------ مولدات الأكواد والباركود ------------------
def generate_product_code():
    """توليد كود منتج فريد مثل PRD-AB12"""
    letters = ''.join(random.choices(string.ascii_uppercase, k=2))
    numbers = ''.join(random.choices(string.digits, k=2))
    return f"PRD-{letters}{numbers}"

def generate_barcode():
    """توليد باركود عشوائي مكون من 13 رقم (يشبه EAN-13)"""
    barcode = [random.randint(0, 9) for _ in range(12)]
    odd_sum = sum(barcode[-1::-2])
    even_sum = sum(barcode[-2::-2])
    check_digit = (10 - ((odd_sum * 3 + even_sum) % 10)) % 10
    barcode.append(check_digit)
    return ''.join(map(str, barcode))

# ------------------ النماذج (Models) ------------------
class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    price = db.Column(db.Float, default=0.0)
    quantity = db.Column(db.Integer, default=0)
    category = db.Column(db.String(100), default="")
    description = db.Column(db.String(500), default="")
    image = db.Column(db.String(200), default="")
    barcode = db.Column(db.String(30), unique=False)
    code = db.Column(db.String(30), unique=False)
    created_at = db.Column(db.String(50), default=lambda: datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

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
    product_name = db.Column(db.String(200))
    quantity = db.Column(db.Integer)
    price = db.Column(db.Float)
    total = db.Column(db.Float)

class DailySale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(200))
    quantity = db.Column(db.Integer)
    price = db.Column(db.Float)
    total = db.Column(db.Float)
    sale_time = db.Column(db.String(20))

class CashTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float)
    note = db.Column(db.String(300))
    date = db.Column(db.DateTime, default=datetime.utcnow)

# ------------------ تهيئة قاعدة البيانات ------------------
with app.app_context():
    db.create_all()
    try:
        tables = db.engine.table_names()
    except Exception:
        tables = []
    print("✅ Database tables created successfully:", tables)

# ------------------ Routes ------------------

@app.route('/')
def index():
    q = request.args.get('q', '').strip()
    if q:
        products = Product.query.filter(
            (Product.name.contains(q)) |
            (Product.code.contains(q)) |
            (Product.barcode.contains(q))
        ).all()
    else:
        products = Product.query.all()
    return render_template('index.html', products=products, q=q)

@app.route('/api/product/<int:pid>')
def get_product(pid):
    p = Product.query.get(pid)
    if not p:
        return jsonify({'error': 'Product not found'}), 404
    return jsonify({'id': p.id, 'name': p.name, 'price': p.price, 'quantity': p.quantity})

@app.route('/api/checkout', methods=['POST'])
def api_checkout():
    payload = request.get_json()
    if not payload:
        return jsonify({'error': 'Invalid payload'}), 400

    cart = payload.get('cart', [])
    payment_method = payload.get('payment_method', 'نقدي')
    if not cart:
        return jsonify({'error': 'cart empty'}), 400

    # حساب الإجمالي
    try:
        total_amount = sum(Decimal(str(item['price'])) * int(item['quantity']) for item in cart)
    except Exception:
        return jsonify({'error': 'invalid cart data'}), 400

    receipt_number = f"RCP{datetime.now().strftime('%Y%m%d%H%M%S')}"
    receipt = Receipt(
        receipt_number=receipt_number,
        date=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        total=float(total_amount),
        payment_method=payment_method
    )
    db.session.add(receipt)
    db.session.flush()

    # حفظ عناصر الفاتورة وتحديث المخزون وتسجيل المبيعات اليومية
    for it in cart:
        pid = it.get('id')
        name = it.get('name')
        qty = int(it.get('quantity'))
        price = Decimal(str(it.get('price')))
        total = float(price * qty)

        ri = ReceiptItem(
            receipt_id=receipt.id,
            product_id=pid,
            product_name=name,
            quantity=qty,
            price=float(price),
            total=total
        )
        db.session.add(ri)

        product = Product.query.get(pid)
        if product:
            product.quantity = max(0, product.quantity - qty)

        ds = DailySale(
            product_name=name,
            quantity=qty,
            price=float(price),
            total=total,
            sale_time=datetime.now().strftime('%H:%M:%S')
        )
        db.session.add(ds)

    # إضافة عملية للخزنة تلقائيًا
    cash = CashTransaction(
        amount=float(total_amount),
        note=f"مبيعات ({payment_method}) - فاتورة {receipt_number}"
    )
    db.session.add(cash)

    db.session.commit()
    return jsonify({'success': True, 'receipt_number': receipt_number, 'total': float(total_amount)}), 200

@app.route('/reports')
def reports():
    receipts = Receipt.query.order_by(Receipt.id.desc()).limit(200).all()
    sales = DailySale.query.order_by(DailySale.id.desc()).limit(200).all()
    balance = sum(t.amount for t in CashTransaction.query.all()) or 0.0
    total_revenue = sum(r.total for r in receipts) or 0.0
    return render_template('reports.html', receipts=receipts, sales=sales, balance=balance, total_revenue=total_revenue)

@app.route('/cash', methods=['GET', 'POST'])
def cash():
    if request.method == 'POST':
        # إضافة/خصم يدوي للخزنة
        try:
            amount = float(request.form.get('amount'))
        except Exception:
            flash('أدخل قيمة صحيحة', 'danger')
            return redirect(url_for('cash'))
        note = request.form.get('note', '')
        tx = CashTransaction(amount=amount, note=note)
        db.session.add(tx)
        db.session.commit()
        flash('تم تحديث الخزنة', 'success')
        return redirect(url_for('cash'))

    transactions = CashTransaction.query.order_by(CashTransaction.date.desc()).all()
    balance = sum(t.amount for t in transactions) or 0.0
    return render_template('cash.html', transactions=transactions, balance=balance)

@app.route('/add_product', methods=['GET', 'POST'])
def add_product_web():
    if request.method == 'POST':
        name = request.form.get('name')
        price = request.form.get('price')
        quantity = request.form.get('quantity')
        category = request.form.get('category') or ''
        desc = request.form.get('description') or ''

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

@app.route('/delete_product/<int:pid>', methods=['POST'])
def delete_product(pid):
    p = Product.query.get(pid)
    if not p:
        flash('المنتج غير موجود', 'warning')
        return redirect(url_for('index'))
    db.session.delete(p)
    db.session.commit()
    flash('تم حذف المنتج', 'info')
    return redirect(url_for('index'))

# ------------------ تشغيل التطبيق ------------------
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
