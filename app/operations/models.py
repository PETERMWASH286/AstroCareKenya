from datetime import datetime

from flask import current_app
from app.extensions import db



class PettyCashRequest(db.Model):
    __tablename__ = 'petty_cash_requests'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    requester_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    petty_cash_account_id = db.Column(db.Integer, db.ForeignKey('petty_cash_accounts.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, approved, denied
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    approved_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    approval_notes = db.Column(db.Text, nullable=True)

    # Relationships
    requester = db.relationship('User', foreign_keys=[requester_id], backref='petty_cash_requests')
    petty_cash_account = db.relationship('PettyCash', backref='requests')
    approver = db.relationship('User', foreign_keys=[approved_by], backref='approved_petty_cash_requests')

    __table_args__ = (
        db.Index('ix_petty_cash_requests_status', 'status'),
        db.Index('ix_petty_cash_requests_created_at', 'created_at'),
    )

    def __repr__(self):
        return f'<PettyCashRequest {self.id} - {self.amount} {self.status}>'
    
    
    


# ----------------------------------------------------------------------
# Supplier model for operations (separate from general suppliers)
# ----------------------------------------------------------------------
class OperationsSupplier(db.Model):
    __tablename__ = 'operations_suppliers'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    contact_person = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    address = db.Column(db.Text)
    category = db.Column(db.String(50))  # e.g., food, medical supplies, spare parts
    rating = db.Column(db.Integer, default=3)  # 1-5
    lead_time_days = db.Column(db.Integer, default=7)
    payment_terms = db.Column(db.String(50))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<OperationsSupplier {self.name}>'

class OperationsSupplierAccount(db.Model):
    __tablename__ = 'operations_supplier_accounts'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('operations_suppliers.id'), nullable=False, unique=True)
    current_balance = db.Column(db.Float, default=0.0)
    currency = db.Column(db.String(10), default='KES')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    supplier = db.relationship('OperationsSupplier', backref='account')


class ProcurementSupplierInvoice(db.Model):
    __tablename__ = 'procurement_supplier_invoices'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('procurement_orders.id'), nullable=False)
    receiving_id = db.Column(db.Integer, db.ForeignKey('procurement_receivings.id'), nullable=False)
    invoice_number = db.Column(db.String(50), unique=True, nullable=False)
    invoice_date = db.Column(db.DateTime, default=datetime.utcnow)
    amount = db.Column(db.Float, nullable=False)
    paid_amount = db.Column(db.Float, default=0.0, nullable=False)   # <-- non‑nullable with default
    status = db.Column(db.String(20), default='pending')
    due_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text)

    order = db.relationship('ProcurementOrder', backref='invoices')
    receiving = db.relationship('ProcurementReceiving', backref='invoice')
    payments = db.relationship('OperationsSupplierPayment', back_populates='invoice', cascade='all, delete-orphan')  # <-- back_populates

    @property
    def balance_due(self):
        return self.amount - self.paid_amount   # now both are floats

    def update_status(self):
        if self.balance_due <= 0:
            self.status = 'paid'
        elif self.paid_amount > 0:
            self.status = 'partially_paid'
        else:
            self.status = 'pending'


class OperationsSupplierPayment(db.Model):
    __tablename__ = 'operations_supplier_payments'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    supplier_account_id = db.Column(db.Integer, db.ForeignKey('operations_supplier_accounts.id'), nullable=False)
    invoice_id = db.Column(db.Integer, db.ForeignKey('procurement_supplier_invoices.id'), nullable=False)
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)
    amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(50))
    reference = db.Column(db.String(100))
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    supplier_account = db.relationship('OperationsSupplierAccount', backref='payments')
    invoice = db.relationship('ProcurementSupplierInvoice', back_populates='payments')  # <-- back_populates
    creator = db.relationship('User', foreign_keys=[created_by], backref='supplier_payments')
# ----------------------------------------------------------------------
# Department Inventory Models
# ----------------------------------------------------------------------
class KitchenInventory(db.Model):
    __tablename__ = 'kitchen_inventory'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    quantity = db.Column(db.Float, nullable=False, default=0)
    unit = db.Column(db.String(20), default='pcs')
    reorder_level = db.Column(db.Float, default=10)
    location = db.Column(db.String(100))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    category = db.Column(db.String(100), nullable=True)  # NEW

    def __repr__(self):
        return f'<KitchenInventory {self.name}>'
    
    
    @property
    def latest_unit_price(self):
        cost = KitchenCost.query.filter_by(item_id=self.id).order_by(KitchenCost.date.desc()).first()
        return cost.unit_price if cost else 0.0
    

    
    
class KitchenUsageLog(db.Model):
    __tablename__ = 'kitchen_usage_logs'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('kitchen_inventory.id'), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    date_used = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text)
    recorded_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    item = db.relationship('KitchenInventory', backref='usage_logs')
    recorder = db.relationship('User', foreign_keys=[recorded_by], backref='kitchen_usage_logs')



class KitchenBudget(db.Model):
    __tablename__ = 'kitchen_budgets'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    month = db.Column(db.Integer, nullable=False)  # 1-12
    year = db.Column(db.Integer, nullable=False)
    category = db.Column(db.String(50), nullable=False)  # e.g., Vegetables, Meat, Dairy, Dry Goods
    allocated_amount = db.Column(db.Float, nullable=False, default=0.0)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<KitchenBudget {self.year}-{self.month:02d} {self.category}>'


class KitchenCost(db.Model):
    __tablename__ = 'kitchen_costs'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('kitchen_inventory.id'), nullable=False)
    unit_price = db.Column(db.Float, nullable=False)  # price per unit at time of usage
    date = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    item = db.relationship('KitchenInventory', backref='costs')
    creator = db.relationship('User', foreign_keys=[created_by])


class KitchenMenu(db.Model):
    __tablename__ = 'kitchen_menus'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    description = db.Column(db.Text)
    preparation_time = db.Column(db.Integer)  # in minutes
    servings = db.Column(db.Integer, default=1)
    image_url = db.Column(db.String(500))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    items = db.relationship('KitchenMenuItem', back_populates='menu', cascade='all, delete-orphan')
    plans = db.relationship('KitchenMenuPlan', back_populates='menu', cascade='all, delete-orphan')
    daily_plans = db.relationship('KitchenDailyPlan', back_populates='menu', cascade='all, delete-orphan')
    @property
    def cost_per_serving(self):
        total = sum(item.quantity * (item.item.latest_unit_price or 0) for item in self.items)
        return total / self.servings if self.servings > 0 else 0

    def __repr__(self):
        return f'<KitchenMenu {self.name}>'


class KitchenMenuItem(db.Model):
    __tablename__ = 'kitchen_menu_items'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    menu_id = db.Column(db.Integer, db.ForeignKey('kitchen_menus.id'), nullable=False)
    inventory_id = db.Column(db.Integer, db.ForeignKey('kitchen_inventory.id'), nullable=False)
    quantity = db.Column(db.Float, nullable=False)  # quantity needed for the recipe
    notes = db.Column(db.Text)

    menu = db.relationship('KitchenMenu', back_populates='items')
    item = db.relationship('KitchenInventory', backref='menu_items')

    def __repr__(self):
        return f'<KitchenMenuItem {self.menu.name} -> {self.item.name}>'


class KitchenMenuPlan(db.Model):
    __tablename__ = 'kitchen_menu_plans'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    meal_type = db.Column(db.String(20), nullable=False)  # breakfast, lunch, dinner, snack
    menu_id = db.Column(db.Integer, db.ForeignKey('kitchen_menus.id'), nullable=False)
    servings_planned = db.Column(db.Integer, default=1)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    menu = db.relationship('KitchenMenu', back_populates='plans')
    
    
class KitchenDailyPlan(db.Model):
    __tablename__ = 'kitchen_daily_plans'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    meal_type = db.Column(db.String(20), nullable=False)  # breakfast, lunch, dinner
    menu_id = db.Column(db.Integer, db.ForeignKey('kitchen_menus.id'), nullable=True)
    servings = db.Column(db.Integer, default=1)
    manual_ingredients = db.Column(db.Text)  # JSON string: [{"name": "tomatoes", "quantity": 2, "unit": "kg", "cost": 150}]
    estimated_cost = db.Column(db.Float, nullable=True)  # override if manual total is provided
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    menu = db.relationship('KitchenMenu', back_populates='daily_plans')

    @property
    def total_cost(self):
        if self.estimated_cost is not None:
            return self.estimated_cost
        total = 0.0
        if self.menu:
            total += self.menu.cost_per_serving * self.servings
        # Parse manual_ingredients if stored as JSON
        if self.manual_ingredients:
            try:
                import json
                ingredients = json.loads(self.manual_ingredients)
                for ing in ingredients:
                    total += ing.get('cost', 0.0)
            except:
                pass
        return total

    def __repr__(self):
        return f'<KitchenDailyPlan {self.date} {self.meal_type}>'


class StoreInventory(db.Model):
    __tablename__ = 'store_inventory'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    quantity = db.Column(db.Float, nullable=False, default=0)
    unit = db.Column(db.String(20), default='pcs')
    reorder_level = db.Column(db.Float, default=10)
    location = db.Column(db.String(100))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    category = db.Column(db.String(100), nullable=True)  # NEW
    is_tracked = db.Column(db.Boolean, default=False)  # Whether items are tracked individually
    tags = db.relationship('ItemTag', back_populates='item', cascade='all, delete-orphan')
    def __repr__(self):
        return f'<StoreInventory {self.name}>'
    
    
    
class ItemTag(db.Model):
    __tablename__ = 'item_tags'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('store_inventory.id'), nullable=False)
    tag_number = db.Column(db.String(100), unique=True, nullable=False)
    status = db.Column(db.String(20), default='available')  # available, assigned, lost, damaged, retired
    purchase_date = db.Column(db.Date)
    expiry_date = db.Column(db.Date)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    item = db.relationship('StoreInventory', back_populates='tags')
    assignments = db.relationship('ItemAssignment', back_populates='tag', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<ItemTag {self.tag_number}>'


class ItemAssignment(db.Model):
    __tablename__ = 'item_assignments'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    tag_id = db.Column(db.Integer, db.ForeignKey('item_tags.id'), nullable=False)
    assigned_to = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    assigned_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    due_back = db.Column(db.Date, nullable=True)
    returned_at = db.Column(db.DateTime)
    notes = db.Column(db.Text)

    tag = db.relationship('ItemTag', back_populates='assignments')
    assignee = db.relationship('User', foreign_keys=[assigned_to], backref='assigned_items')
    assigner = db.relationship('User', foreign_keys=[assigned_by], backref='item_assignments_made')

    def __repr__(self):
        return f'<ItemAssignment {self.tag.tag_number} -> {self.assignee.full_name}>'


class StoreMaintenance(db.Model):
    __tablename__ = 'store_maintenance'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('store_inventory.id'), nullable=False)
    maintenance_date = db.Column(db.DateTime, default=datetime.utcnow)
    type = db.Column(db.String(20))  # routine, repair, emergency
    description = db.Column(db.Text, nullable=False)
    cost = db.Column(db.Float, default=0.0)
    performed_by = db.Column(db.String(100))
    notes = db.Column(db.Text)
    transaction_reference = db.Column(db.String(100))
    petty_cash_account_id = db.Column(db.Integer, db.ForeignKey('petty_cash_accounts.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    tag_id = db.Column(db.Integer, db.ForeignKey('item_tags.id'), nullable=True)
    tag = db.relationship('ItemTag', backref='maintenance_records')
    
    
    item = db.relationship('StoreInventory', backref='maintenance_records')
    petty_cash_account = db.relationship('PettyCash', backref='store_maintenance')

    def __repr__(self):
        return f'<StoreMaintenance {self.id} - {self.item.name}>'


class FarmInventory(db.Model):
    __tablename__ = 'farm_inventory'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    quantity = db.Column(db.Float, nullable=False, default=0)
    unit = db.Column(db.String(20), default='pcs')
    reorder_level = db.Column(db.Float, default=10)
    location = db.Column(db.String(100))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    category = db.Column(db.String(100), nullable=True)  # NEW
    type = db.Column(db.String(20), default='input')  # input, harvest
    price_per_unit = db.Column(db.Float, default=0.0)
    def __repr__(self):
        return f'<FarmInventory {self.name}>'



class FarmLivestock(db.Model):
    __tablename__ = 'farm_livestock'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    breed = db.Column(db.String(100))
    quantity = db.Column(db.Integer, default=0)
    unit = db.Column(db.String(20), default='heads')
    purchase_date = db.Column(db.Date)
    purchase_cost = db.Column(db.Float, default=0.0)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    health_records = db.relationship('FarmHealthRecord', backref='livestock', lazy='dynamic')
    # Use back_populates instead of backref
    sales = db.relationship('FarmRevenue', back_populates='livestock', lazy='dynamic')

class FarmHealthRecord(db.Model):
    __tablename__ = 'farm_health_records'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    livestock_id = db.Column(db.Integer, db.ForeignKey('farm_livestock.id'), nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    type = db.Column(db.String(50))
    description = db.Column(db.Text)
    cost = db.Column(db.Float, default=0.0)
    performed_by = db.Column(db.String(100))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class FarmCrop(db.Model):
    __tablename__ = 'farm_crops'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    variety = db.Column(db.String(100))
    planting_date = db.Column(db.Date)
    expected_harvest_date = db.Column(db.Date)
    area = db.Column(db.Float)
    quantity_planted = db.Column(db.Float)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    harvests = db.relationship('FarmHarvest', backref='crop', lazy='dynamic')

class FarmHarvest(db.Model):
    __tablename__ = 'farm_harvests'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    crop_id = db.Column(db.Integer, db.ForeignKey('farm_crops.id'), nullable=False)
    harvest_date = db.Column(db.DateTime, default=datetime.utcnow)
    quantity = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(20), default='kg')
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    inventory_entry_id = db.Column(db.Integer, db.ForeignKey('farm_inventory.id'), nullable=True)

class FarmExpense(db.Model):
    __tablename__ = 'farm_expenses'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    category = db.Column(db.String(50))
    description = db.Column(db.Text, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(50))
    reference = db.Column(db.String(100))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class FarmRevenue(db.Model):
    __tablename__ = 'farm_revenues'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    source = db.Column(db.String(50))  # livestock, crop, other
    description = db.Column(db.Text)
    quantity_sold = db.Column(db.Float)
    unit_price = db.Column(db.Float)
    total_amount = db.Column(db.Float, nullable=False)
    customer = db.Column(db.String(100))
    payment_method = db.Column(db.String(50))
    reference = db.Column(db.String(100))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    inventory_item_id = db.Column(db.Integer, db.ForeignKey('farm_inventory.id'), nullable=True)
    livestock_id = db.Column(db.Integer, db.ForeignKey('farm_livestock.id'), nullable=True)
    crop_id = db.Column(db.Integer, db.ForeignKey('farm_crops.id'), nullable=True)   # New column

    inventory_item = db.relationship('FarmInventory', backref='revenues')
    livestock = db.relationship('FarmLivestock', backref='revenues')
    crop = db.relationship('FarmCrop', backref='revenues')

class FleetInventory(db.Model):
    __tablename__ = 'fleet_inventory'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    quantity = db.Column(db.Float, nullable=False, default=0)
    unit = db.Column(db.String(20), default='pcs')
    reorder_level = db.Column(db.Float, default=10)
    location = db.Column(db.String(100))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<FleetInventory {self.name}>'
    
    
    
class FleetVehicle(db.Model):
    __tablename__ = 'fleet_vehicles'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    registration = db.Column(db.String(20), unique=True, nullable=False)
    make = db.Column(db.String(50), nullable=False)
    model = db.Column(db.String(50), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    capacity = db.Column(db.String(50))
    status = db.Column(db.String(20), default='active')
    insurance_expiry = db.Column(db.Date)
    last_service_date = db.Column(db.Date)
    next_service_km = db.Column(db.Integer)
    current_odometer = db.Column(db.Integer, default=0)
    fuel_type = db.Column(db.String(20))
    notes = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships – use back_populates instead of backref
    maintenance_records = db.relationship('FleetMaintenance', back_populates='vehicle', lazy='dynamic')
    fuel_records = db.relationship('FleetFuel', back_populates='vehicle', lazy='dynamic')
    trips = db.relationship('FleetTrip', back_populates='vehicle', lazy='dynamic')

    def __repr__(self):
        return f'<FleetVehicle {self.registration}>'


class FleetMaintenance(db.Model):
    __tablename__ = 'fleet_maintenance'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey('fleet_vehicles.id'), nullable=False)
    maintenance_date = db.Column(db.DateTime, default=datetime.utcnow)
    type = db.Column(db.String(20))  # routine, repair, emergency
    description = db.Column(db.Text, nullable=False)
    cost = db.Column(db.Float, default=0.0)
    performed_by = db.Column(db.String(100))
    odometer = db.Column(db.Integer)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    vehicle = db.relationship('FleetVehicle', back_populates='maintenance_records')

    def __repr__(self):
        return f'<FleetMaintenance {self.id} - Vehicle {self.vehicle_id}>'


class FleetFuel(db.Model):
    __tablename__ = 'fleet_fuel'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey('fleet_vehicles.id'), nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    liters = db.Column(db.Float, nullable=False)
    cost = db.Column(db.Float, nullable=False)
    odometer = db.Column(db.Integer, nullable=False)
    location = db.Column(db.String(100))
    notes = db.Column(db.Text)
    transaction_reference = db.Column(db.String(100))
    petty_cash_account_id = db.Column(db.Integer, db.ForeignKey('petty_cash_accounts.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    vehicle = db.relationship('FleetVehicle', back_populates='fuel_records')
    petty_cash_account = db.relationship('PettyCash', backref='fuel_records')

    def __repr__(self):
        return f'<FleetFuel {self.id} - {self.liters}L>'


class FleetTrip(db.Model):
    __tablename__ = 'fleet_trips'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey('fleet_vehicles.id'), nullable=False)
    driver = db.Column(db.String(100), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    start_odometer = db.Column(db.Integer, nullable=True)   # made optional
    end_odometer = db.Column(db.Integer, nullable=True)     # made optional
    distance = db.Column(db.Integer)  # calculated or user-provided
    destination = db.Column(db.String(200))  # new field for trip destination
    purpose = db.Column(db.String(200))
    passengers = db.Column(db.Integer)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    vehicle = db.relationship('FleetVehicle', back_populates='trips')


# ----------------------------------------------------------------------
# Procurement Models (using the above inventory models)
# ----------------------------------------------------------------------
class ProcurementRequest(db.Model):
    __tablename__ = 'procurement_requests'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    requester_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    department = db.Column(db.String(50), nullable=False)
    item_name = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(20), default='pcs')
    priority = db.Column(db.String(20), default='medium')
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    approved_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    approval_notes = db.Column(db.Text, nullable=True)
# In app/operations/models.py, inside ProcurementRequest class
    category = db.Column(db.String(100), nullable=True)
    # Relationships
    requester = db.relationship('User', foreign_keys=[requester_id], backref='procurement_requests')
    approver = db.relationship('User', foreign_keys=[approved_by], backref='approved_procurement_requests')
    purchase_order = db.relationship('ProcurementOrder', back_populates='request', uselist=False)

    def __repr__(self):
        return f'<ProcurementRequest {self.id} - {self.item_name}>'


class ProcurementOrder(db.Model):
    __tablename__ = 'procurement_orders'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey('procurement_requests.id'), nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('operations_suppliers.id'), nullable=False)
    order_number = db.Column(db.String(50), unique=True, nullable=False)
    order_date = db.Column(db.DateTime, default=datetime.utcnow)
    expected_delivery = db.Column(db.Date, nullable=True)
    total_amount = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default='ordered')
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    unit_price = db.Column(db.Float, default=0.0)

    # Relationships
    request = db.relationship('ProcurementRequest', back_populates='purchase_order')
    supplier = db.relationship('OperationsSupplier', backref='procurement_orders')
    creator = db.relationship('User', foreign_keys=[created_by], backref='created_procurement_orders')
    deliveries = db.relationship('ProcurementReceiving', back_populates='order', cascade='all, delete-orphan')

    def generate_order_number(self):
        date_str = datetime.utcnow().strftime('%Y%m%d')
        last = ProcurementOrder.query.order_by(ProcurementOrder.id.desc()).first()
        seq = (last.id + 1) if last else 1
        return f"PO-{date_str}-{seq:04d}"


class ProcurementReceiving(db.Model):
    __tablename__ = 'procurement_receivings'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('procurement_orders.id'), nullable=False)
    received_date = db.Column(db.DateTime, default=datetime.utcnow)
    quantity_received = db.Column(db.Float, nullable=False)
    batch_number = db.Column(db.String(50))
    expiration_date = db.Column(db.Date)
    condition = db.Column(db.String(50), default='good')
    notes = db.Column(db.Text)
    received_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    order = db.relationship('ProcurementOrder', back_populates='deliveries')
    receiver = db.relationship('User', foreign_keys=[received_by], backref='received_procurements')

    def after_receive(self):
        from datetime import timedelta

        order = self.order
        # Update order status
        total_received = sum(r.quantity_received for r in order.deliveries)
        if total_received >= order.request.quantity:
            order.status = 'received'
        else:
            order.status = 'partially_received'
        db.session.commit()

        # Add to department inventory
        request = order.request
        location_map = {
            'kitchen': 'Kitchen Store',
            'store': 'Main Store',
            'farm': 'Farm Store',
            'fleet': 'Fleet Garage'
        }
        default_location = location_map.get(request.department, '')

        if request.department == 'kitchen':
            existing = KitchenInventory.query.filter_by(name=request.item_name).first()
            if existing:
                existing.quantity += self.quantity_received
                # Optionally update category if empty
                if not existing.category and request.category:
                    existing.category = request.category
            else:
                new = KitchenInventory(
                    name=request.item_name,
                    category=request.category,   # NEW
                    quantity=self.quantity_received,
                    unit=request.unit,
                    location=default_location
                )
                db.session.add(new)
        elif request.department == 'store':
            existing = StoreInventory.query.filter_by(name=request.item_name).first()
            if existing:
                existing.quantity += self.quantity_received
                if not existing.category and request.category:
                    existing.category = request.category
            else:
                new = StoreInventory(
                    name=request.item_name,
                    category=request.category,
                    quantity=self.quantity_received,
                    unit=request.unit,
                    location=default_location
                )
                db.session.add(new)
        elif request.department == 'farm':
            existing = FarmInventory.query.filter_by(name=request.item_name).first()
            if existing:
                existing.quantity += self.quantity_received
                if not existing.category and request.category:
                    existing.category = request.category
            else:
                new = FarmInventory(
                    name=request.item_name,
                    category=request.category,
                    quantity=self.quantity_received,
                    unit=request.unit,
                    location=default_location
                )
                db.session.add(new)
        elif request.department == 'fleet':
            existing = FleetInventory.query.filter_by(name=request.item_name).first()
            if existing:
                existing.quantity += self.quantity_received
                if not existing.category and request.category:
                    existing.category = request.category
            else:
                new = FleetInventory(
                    name=request.item_name,
                    category=request.category,
                    quantity=self.quantity_received,
                    unit=request.unit,
                    location=default_location
                )
                db.session.add(new)

        # Create supplier invoice
        amount = self.quantity_received * order.unit_price
        invoice_number = f"INV-{order.order_number}-{self.id}"
        invoice = ProcurementSupplierInvoice(
            order_id=order.id,
            receiving_id=self.id,
            invoice_number=invoice_number,
            invoice_date=datetime.utcnow(),
            amount=amount,
            due_date=order.expected_delivery + timedelta(days=30) if order.expected_delivery else None,
            notes=f"Delivery {self.id} for order {order.order_number}"
        )
        db.session.add(invoice)

        # Update supplier account balance
        account = OperationsSupplierAccount.query.filter_by(supplier_id=order.supplier_id).first()
        if not account:
            account = OperationsSupplierAccount(supplier_id=order.supplier_id, current_balance=0.0)
            db.session.add(account)
        account.current_balance += amount
        db.session.commit()