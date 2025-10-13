
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date
import random, string
from decimal import Decimal

app = Flask(__name__)
app.secret_key = "secret"
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///shop.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
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
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    category = db.Column(db.String(50))
    description = db.Column(db.String(200))
    image = db.Column(db.String(200))
    barcode = db.Column(db.String(20))
    code = db.Column(db.String(20))
    created_at = db.Column(db.String(50))

class Receipt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    receipt_number = db.Column(db.String(50), unique=True)
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
    sale_date = db.Column(db.String(20))

class CashTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
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
        products = Product.query.filter(Product.name.contains(q) | Product.code.contains(q)).all()
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
    
    try:
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
                if product.quantity < qty:
                    return jsonify({'error': f'الكمية غير كافية للمنتج {name}'}), 400
                product.quantity = max(0, product.quantity - qty)

            db.session.add(DailySale(
                product_name=name,
                quantity=qty,
                price=float(price),
                total=float(total),
                sale_time=datetime.now().strftime('%H:%M:%S'),
                sale_date=date.today().isoformat()
            ))

        # 💰 تحديث الخزنة تلقائيًا
        db.session.add(CashTransaction(
            amount=float(total_amount),
            note=f"مبيعات ({payment_method}) - فاتورة {receipt_number}"
        ))

        db.session.commit()
        return jsonify({'success': True, 'receipt_number': receipt_number, 'total': float(total_amount)})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

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
    today = date.today().isoformat()
    daily_sales = DailySale.query.filter(DailySale.sale_date == today).all()
    
    # إحصائيات المبيعات
    total_revenue = sum(sale.total for sale in daily_sales)
    total_sales_count = len(daily_sales)
    
    # أعلى المنتجات مبيعاً
    from collections import defaultdict
    product_sales = defaultdict(int)
    for sale in daily_sales:
        product_sales[sale.product_name] += sale.quantity
    
    top_products = sorted(product_sales.items(), key=lambda x: x[1], reverse=True)[:5]
    
    # المنتجات ذات المخزون المنخفض
    low_stock = Product.query.filter(Product.quantity < 10).order_by(Product.quantity.asc()).all()
    
    return render_template('reports.html',
                         today_date=date.today().strftime('%Y-%m-%d'),
                         total_revenue=total_revenue,
                         total_sales_count=total_sales_count,
                         top_products=top_products,
                         low_stock=low_stock,
                         daily_sales=daily_sales)

# 🧩 صفحة الخزنة
@app.route('/cash', methods=['GET', 'POST'])
def cash():
    if request.method == 'POST':
        amount = request.form.get('amount')
        note = request.form.get('note', '')
        
        if not amount:
            flash('❌ من فضلك أدخل المبلغ', 'danger')
            return redirect(url_for('cash'))
        
        try:
            transaction = CashTransaction(
                amount=float(amount),
                note=note
            )
            db.session.add(transaction)
            db.session.commit()
            flash('✅ تم حفظ العملية بنجاح', 'success')
        except ValueError:
            flash('❌ المبلغ غير صحيح', 'danger')
        
        return redirect(url_for('cash'))
    
    transactions = CashTransaction.query.order_by(CashTransaction.date.desc()).all()
    total = sum(t.amount for t in transactions)
    return render_template('cash.html', transactions=transactions, total=total)

# 🧩 صفحة إضافة منتج
@app.route('/add_product', methods=['GET', 'POST'])
def add_product_web():
    if request.method == 'POST':
        product_id = request.form.get('product_id')
        product_name = request.form.get('product_name')
        product_price = request.form.get('product_price')
        product_quantity = request.form.get('product_quantity')
        product_category = request.form.get('product_category')
        product_barcode = request.form.get('product_barcode')
        product_description = request.form.get('product_description')

        if not all([product_name, product_price, product_quantity]):
            flash('❌ من فضلك أدخل البيانات الأساسية للمنتج', 'danger')
            return redirect(url_for('add_product_web'))

        try:
            new_product = Product(
                name=product_name,
                price=float(product_price),
                quantity=int(product_quantity),
                category=product_category,
                description=product_description,
                barcode=product_barcode or generate_barcode(),
                code=product_id or generate_product_code(),
                created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )
            db.session.add(new_product)
            db.session.commit()
            flash('✅ تم إضافة المنتج بنجاح!', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            flash(f'❌ خطأ في إضافة المنتج: {str(e)}', 'danger')
    
    # توليد باركود تلقائي للعرض
    barcode = generate_barcode()
    return render_template('add_product.html', barcode=barcode)

if __name__ == '__main__':
    app.run(debug=True)

