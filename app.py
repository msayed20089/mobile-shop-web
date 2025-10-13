import os
from datetime import datetime
from decimal import Decimal

from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from urllib.parse import urlparse

# ---------- إعداد التطبيق ----------
app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET', 'change_this_secret')

# اختار قاعدة البيانات: لو ENV متوفر (DATABASE_URL) نستخدمه (Postgres on Railway)، وإلا SQLite محلي
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    # Heroku/Railway style DATABASE_URL may start with postgres:// -> SQLAlchemy needs postgresql://
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///mobile_shop.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ---------- نماذج قواعد البيانات (Models) ----------
class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)  # يسمح بتعيين id يدويًا
    name = db.Column(db.String, nullable=False)
    price = db.Column(db.Numeric(10,2), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    category = db.Column(db.String, nullable=False, default='غير محدد')
    description = db.Column(db.Text)
    image_path = db.Column(db.String)
    barcode = db.Column(db.String)
    created_date = db.Column(db.String)
    supplier = db.Column(db.String)

class CashTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)  # موجب أو سالب
    note = db.Column(db.String(200))
    date = db.Column(db.DateTime, default=datetime.utcnow)


class Receipt(db.Model):
    __tablename__ = 'receipts'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    receipt_number = db.Column(db.String, nullable=False)
    date = db.Column(db.String, nullable=False)
    total = db.Column(db.Numeric(12,2), nullable=False)
    payment_method = db.Column(db.String, nullable=False)
    customer_name = db.Column(db.String)
    customer_phone = db.Column(db.String)
    discount = db.Column(db.Numeric(10,2), default=0)
    tax = db.Column(db.Numeric(10,2), default=0)
    items = db.relationship('ReceiptItem', backref='receipt', cascade="all, delete-orphan")

class ReceiptItem(db.Model):
    __tablename__ = 'receipt_items'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    receipt_id = db.Column(db.Integer, db.ForeignKey('receipts.id'))
    product_id = db.Column(db.Integer)
    product_name = db.Column(db.String, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Numeric(10,2), nullable=False)
    total = db.Column(db.Numeric(12,2), nullable=False)

class DailySale(db.Model):
    __tablename__ = 'daily_sales'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    product_name = db.Column(db.String, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Numeric(10,2), nullable=False)
    total = db.Column(db.Numeric(12,2), nullable=False)
    sale_time = db.Column(db.String, nullable=False)  # store HH:MM:SS or full timestamp

# ---------- تهيئة و seed لقاعدة البيانات ----------
def seed_defaults():
    # إذا ما فيش منتجات نضيف الافتراضية
    if Product.query.count() == 0:
        now = datetime.now().strftime('%Y-%m-%d')
        defaults = [
            (1, "سامسونج جالاكسي S24", 4500.0, 10, "هواتف", "هاتف سامسونج الرائد بشاشة 6.8 بوصة", "samsung_s24.jpg", "1234567890123", now, ""),
            (2, "آيفون 15 برو", 5500.0, 8, "هواتف", "هاتف أبل الرائد بشريحة A17", "iphone15_pro.jpg", "1234567890124", now, ""),
            (3, "شاومي ريدمي نوت 13", 1500.0, 15, "هواتف", "هاتف شاومي بشاشة AMOLED", "xiaomi_note13.jpg", "1234567890125", now, ""),
            (4, "سماعات ايربودز برو", 800.0, 20, "إكسسوارات", "سماعات لاسلكية بإلغاء الضوضاء", "airpods_pro.jpg", "1234567890126", now, ""),
            (5, "حافظة سليكون", 50.0, 30, "إكسسوارات", "حافظة واقية من السيلكون", "silicon_case.jpg", "1234567890127", now, ""),
            (6, "شاحن سريع 45 وات", 120.0, 25, "إكسسوارات", "شاحن سريع بشهادة الجودة", "fast_charger.jpg", "1234567890128", now, ""),
            (7, "شريحة اتصال 4G", 20.0, 100, "خدمات", "شريحة اتصال بباقة إنترنت", "sim_card.jpg", "1234567890129", now, ""),
            (8, "باقة إنترنت 100 جيجا", 200.0, 50, "خدمات", "باقة إنترنت شهرية 100 جيجا", "internet_package.jpg", "1234567890130", now, ""),
            (9, "كارت شحن فودافون 10 جنيه", 10.0, 100, "كروت شحن", "كارت شحن فودافون فئة 10 جنيه", "vodafone10.jpg", "2000000000001", now, ""),
            (10, "كارت شحن أورانج 20 جنيه", 20.0, 80, "كروت شحن", "كارت شحن أورانج فئة 20 جنيه", "orange20.jpg", "2000000000002", now, ""),
            (11, "كارت شحن اتصالات 50 جنيه", 50.0, 60, "كروت شحن", "كارت شحن اتصالات فئة 50 جنيه", "etisalat50.jpg", "2000000000003", now, ""),
            (12, "كارت شحن WE 100 جنيه", 100.0, 40, "كروت شحن", "كارت شحن WE فئة 100 جنيه", "we100.jpg", "2000000000004", now, "")
        ]
        for p in defaults:
            prod = Product(
                id=p[0],
                name=p[1],
                price=Decimal(str(p[2])),
                quantity=p[3],
                category=p[4],
                description=p[5],
                image_path=p[6],
                barcode=p[7],
                created_date=p[8],
                supplier=p[9]
            )
            db.session.add(prod)
        db.session.commit()

# ✅ استدعاء تهيئة قاعدة البيانات مباشرة بعد إنشاء التطبيق
with app.app_context():
    db.create_all()
    seed_defaults()


# ---------- واجهات الويب (Routes) ----------
@app.route('/')
def index():
    # صفحة المنتجات (تسمح بالبحث بالـ q param)
    q = request.args.get('q', '').strip()
    if q:
        like = f"%{q}%"
        products = Product.query.filter(
            (Product.name.ilike(like)) |
            (func.cast(Product.id, db.String).ilike(like)) |
            (Product.barcode.ilike(like))
        ).all()
    else:
        products = Product.query.all()
    return render_template('index.html', products=products, q=q)

@app.route('/cash', methods=['GET', 'POST'])
def cash():
    if request.method == 'POST':
        amount = float(request.form['amount'])
        note = request.form.get('note', '')
        tx = CashTransaction(amount=amount, note=note)
        db.session.add(tx)
        db.session.commit()
        flash('تم تحديث الخزنة بنجاح', 'success')
        return redirect('/cash')

    transactions = CashTransaction.query.order_by(CashTransaction.date.desc()).all()
    total = sum(tx.amount for tx in transactions)
    return render_template('cash.html', transactions=transactions, total=total)


@app.route('/product/<int:product_id>')
def product_detail(product_id):
    p = Product.query.get_or_404(product_id)
    return jsonify({
        'id': p.id, 'name': p.name, 'price': str(p.price), 'quantity': p.quantity,
        'category': p.category, 'description': p.description or ''
    })

# API بحث سريع (AJAX)
@app.route('/api/search')
def api_search():
    q = request.args.get('q', '').strip()
    like = f"%{q}%"
    products = Product.query.filter(
        (Product.name.ilike(like)) |
        (func.cast(Product.id, db.String).ilike(like)) |
        (Product.barcode.ilike(like))
    ).limit(50).all()
    data = []
    for p in products:
        data.append({
            'id': p.id, 'name': p.name, 'price': float(p.price), 'quantity': p.quantity, 'category': p.category
        })
    return jsonify(data)

# Checkout endpoint — يتوقع بيانات الكارت (json) ثم يسجل الفاتورة، ويحدث المخزون، ويسجل daily_sales
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
        total=total_amount,
        payment_method=payment_method
    )
    db.session.add(receipt)
    db.session.flush()  # to get receipt.id

    # حفظ عناصر الفاتورة وتحديث المخزون وتسجيل في daily_sales
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
            price=price,
            total=total
        )
        db.session.add(ri)

        # تحديث المخزون
        product = Product.query.get(pid)
        if product:
            product.quantity = max(0, product.quantity - qty)

        # تسجيل البيع اليومي مع الوقت
        ds = DailySale(
            product_name=name,
            quantity=qty,
            price=price,
            total=total,
            sale_time=datetime.now().strftime('%H:%M:%S')
        )
        db.session.add(ds)

    db.session.commit()
    return jsonify({'success': True, 'receipt_number': receipt_number, 'total': float(total_amount)}), 200

# صفحة التقارير
@app.route('/reports')
def reports():
    today_date = datetime.now().strftime('%Y-%m-%d')
    # مبيعات يومية (عدد وسعر)
    todays_receipts = Receipt.query.filter(Receipt.date.ilike(f"{today_date}%")).all()
    total_sales_count = len(todays_receipts)
    total_revenue = sum(r.total for r in todays_receipts) or 0

    # أعلى المنتجات مبيعاً (من receipt_items)
    top = db.session.query(
        ReceiptItem.product_name, func.sum(ReceiptItem.quantity).label('sold')
    ).group_by(ReceiptItem.product_name).order_by(func.sum(ReceiptItem.quantity).desc()).limit(10).all()

    # تقارير المخزون
    low_stock = Product.query.order_by(Product.quantity.asc()).limit(50).all()

    # سجل المبيعات اليومي المفصل (من daily_sales)
    daily_log = DailySale.query.order_by(DailySale.id.desc()).limit(200).all()

    return render_template('reports.html',
                           total_sales_count=total_sales_count,
                           total_revenue=total_revenue,
                           top=top,
                           low_stock=low_stock,
                           daily_log=daily_log,
                           today_date=today_date)

# إضافة منتج جديد عبر واجهة الويب
@app.route('/products/new', methods=['GET','POST'])
def add_product_web():
    if request.method == 'POST':
        try:
            pid = int(request.form.get('product_id') or 0)
            name = request.form['product_name']
            price = Decimal(request.form['product_price'])
            qty = int(request.form['product_quantity'])
            category = request.form.get('product_category') or 'غير محدد'
            barcode = request.form.get('product_barcode') or ''
            supplier = request.form.get('product_supplier') or ''
            desc = request.form.get('product_description') or ''
            created = datetime.now().strftime('%Y-%m-%d')

            if Product.query.get(pid):
                flash('كود المنتج موجود بالفعل', 'danger')
                return redirect(url_for('add_product_web'))

            prod = Product(id=pid, name=name, price=price, quantity=qty, category=category,
                           description=desc, image_path='', barcode=barcode, created_date=created, supplier=supplier)
            db.session.add(prod)
            db.session.commit()
            flash('تم إضافة المنتج بنجاح', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            flash(f'فشل إضافة المنتج: {e}', 'danger')
            return redirect(url_for('add_product_web'))
    else:
        # auto-generate id
        max_id = db.session.query(func.max(Product.id)).scalar() or 0
        next_id = max_id + 1
        # generate barcode simple
        barcode = ''.join(str((random := datetime.now().timestamp()) )[:13])  # cheap uniqueness placeholder
        return render_template('add_product.html', next_id=next_id, barcode=barcode)

@app.route('/delete_product/<int:product_id>', methods=['POST'])
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    flash(f'تم حذف المنتج: {product.name}', 'info')
    return redirect('/')

# API للحصول على تفاصيل المنتج (لعرض المودال)
@app.route('/api/product/<int:pid>')
def api_product(pid):
    p = Product.query.get_or_404(pid)
    return jsonify({'id': p.id, 'name': p.name, 'price': float(p.price), 'quantity': p.quantity, 'category': p.category, 'description': p.description or ''})

class CashTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    note = db.Column(db.String(200))
    date = db.Column(db.DateTime, default=datetime.utcnow)


# endpoint بسيط للحصول على قائمة سريعة للـ cart preview
@app.route('/api/products_all')
def api_products_all():
    products = Product.query.order_by(Product.name).limit(1000).all()
    return jsonify([{'id': p.id, 'name': p.name, 'price': float(p.price), 'quantity': p.quantity} for p in products])

# ---------- تشغيل ----------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
