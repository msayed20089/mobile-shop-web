from flask import Flask, jsonify, request, render_template
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from decimal import Decimal

# إعداد التطبيق وقاعدة البيانات
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///shop.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ========================= النماذج =============================

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    price = db.Column(db.Float)
    quantity = db.Column(db.Integer)

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
    sale_time = db.Column(db.String(50))

# 💰 جدول الخزنة
class CashTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    note = db.Column(db.String(200))
    date = db.Column(db.DateTime, default=datetime.utcnow)

# ========================= المسارات =============================

@app.route('/')
def index():
    q = request.args.get('q', '')
    if q:
        products = Product.query.filter(Product.name.contains(q)).all()
    else:
        products = Product.query.all()
    return render_template('index.html', products=products, q=q)

@app.route('/api/product/<int:pid>')
def get_product(pid):
    p = Product.query.get(pid)
    if not p:
        return jsonify({'error': 'Product not found'}), 404
    return jsonify({'id': p.id, 'name': p.name, 'price': p.price, 'quantity': p.quantity})

# ✅ Checkout مع تحديث الخزنة
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
    db.session.flush()  # للحصول على receipt.id

    # حفظ عناصر الفاتورة وتحديث المخزون
    for it in cart:
        pid = it.get('id')
        name = it.get('name')
        qty = int(it.get('quantity'))
        price = Decimal(str(it.get('price')))
        total = price * qty

        ri = ReceiptItem(
            receipt_id=receipt.id,
            product_id=pid,
            product_name=name,
            quantity=qty,
            price=float(price),
            total=float(total)
        )
        db.session.add(ri)

        product = Product.query.get(pid)
        if product:
            product.quantity = max(0, product.quantity - qty)

        # تسجيل البيع اليومي
        ds = DailySale(
            product_name=name,
            quantity=qty,
            price=float(price),
            total=float(total),
            sale_time=datetime.now().strftime('%H:%M:%S')
        )
        db.session.add(ds)

    # 💵 تسجيل العملية في الخزنة
    cash = CashTransaction(
        amount=float(total_amount),
        note=f"مبيعات ({payment_method}) - فاتورة {receipt_number}"
    )
    db.session.add(cash)

    db.session.commit()
    return jsonify({'success': True, 'receipt_number': receipt_number, 'total': float(total_amount)}), 200

# ✅ عرض صفحة الخزنة
@app.route('/cash')
def cash():
    transactions = CashTransaction.query.order_by(CashTransaction.date.desc()).all()
    balance = sum(t.amount for t in transactions)
    return render_template('cash.html', transactions=transactions, balance=balance)


@app.route('/reports')
def reports():
    receipts = Receipt.query.order_by(Receipt.date.desc()).all()
    sales = DailySale.query.order_by(DailySale.id.desc()).limit(100).all()
    balance = sum(t.amount for t in CashTransaction.query.all())
    total_revenue = sum(r.total for r in receipts)

    return render_template(
        'reports.html',
        receipts=receipts,
        sales=sales,
        balance=balance,
        total_revenue=total_revenue
    )




# ========================= تهيئة قاعدة البيانات =============================
with app.app_context():
    db.create_all()
    print("✅ Database tables created successfully")

# صفحة إضافة منتج من الويب
@app.route('/add_product', methods=['GET', 'POST'])
def add_product_web():
    if request.method == 'POST':
        name = request.form.get('name')
        price = request.form.get('price', type=float)
        quantity = request.form.get('quantity', type=int)
        category = request.form.get('category')
        description = request.form.get('description', '')
        barcode = request.form.get('barcode', '')
        image = request.form.get('image', '')

        if not name or price is None or quantity is None:
            flash('❌ من فضلك أدخل بيانات صحيحة للمنتج', 'danger')
        else:
            new_product = Product(
                name=name,
                price=price,
                quantity=quantity,
                category=category,
                description=description,
                barcode=barcode,
                image=image,
                date_added=datetime.now().strftime('%Y-%m-%d')
            )
            db.session.add(new_product)
            db.session.commit()
            flash('✅ تم إضافة المنتج بنجاح', 'success')
            return redirect(url_for('index'))

    return render_template('add_product.html')


# ========================= التشغيل =============================
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
