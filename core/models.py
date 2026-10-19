from django.db import models

# Create your models here.
class Buyer(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True, default='')  # Google doesn't provide a phone number
    password = models.CharField(max_length=128, blank=True, default="")
    wallet = models.OneToOneField(
        'Wallet',
        on_delete=models.CASCADE,
        related_name='buyer_owner',
        blank=True,
        null=True,
    )

    def __str__(self):
        return self.name

class Address(models.Model):
    buyer = models.ForeignKey(
        Buyer,
        on_delete=models.CASCADE,
        related_name="addresses",
        blank=True,
        null=True,
    )
    seller = models.ForeignKey(
        'Seller',
        on_delete=models.CASCADE,
        related_name="addresses",
        blank=True,
        null=True,
    )
    line1 = models.CharField(max_length=255)
    line2 = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100)
    is_default = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.line1}, {self.city}"
    


class Seller(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True, default='')  # Google doesn't provide a phone number
    password = models.CharField(max_length=128, blank=True, default="")
    wallet = models.OneToOneField(
        'Wallet',
        on_delete=models.CASCADE,
        related_name='seller_owner',
        blank=True,
        null=True,
    )

    def __str__(self):
        return self.name


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Categories"


class Product(models.Model):
    seller = models.ForeignKey(
        Seller,
        on_delete=models.CASCADE,
        related_name="products"
    )
    name = models.CharField(max_length=255)
    description = models.TextField()
    image_url = models.URLField(blank=True, null=True)
    image = models.ImageField(upload_to='product_images/', blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    sku = models.CharField(max_length=100, unique=True)
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        related_name='products',
        blank=True,
        null=True,
    )

    def __str__(self):
        return self.name


class Inventory(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="inventories"
    )
    quantity = models.IntegerField()
    warehouse_location = models.ForeignKey(
        Address,
        on_delete=models.SET_NULL,
        related_name="warehouses",
        blank=True,
        null=True,
    )
    updated_at = models.DateTimeField(auto_now=True)


class Cart(models.Model):
    buyer = models.OneToOneField(
        Buyer,
        on_delete=models.CASCADE,
        related_name="cart"
    )
    status = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class CartProduct(models.Model):
    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name="cart_items"
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE
    )
    quantity = models.IntegerField()

    class Meta:
        unique_together = ("cart", "product")


class Order(models.Model):
    buyer = models.ForeignKey(
        Buyer,
        on_delete=models.CASCADE,
        related_name="orders"
    )
    address = models.ForeignKey(
        Address,
        on_delete=models.PROTECT,
        related_name="orders"
    )
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=50)
    placed_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateField(blank=True, null=True)


class OrderItem(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
    ]
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items"
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT
    )
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    line_total = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Pending')

    class Meta:
        unique_together = ("order", "product")

    def __str__(self):
        return f"OrderItem #{self.id} — {self.product.name} (Order #{self.order_id})"


class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('order_placed', 'Order Placed'),
        ('approval_request', 'Approval Request'),
        ('order_confirmed', 'Order Confirmed'),
        ('order_rejected', 'Order Rejected'),
        ('item_approved', 'Item Approved'),
        ('item_rejected', 'Item Rejected'),
        ('wallet_debited', 'Wallet Debited'),
        ('wallet_credited', 'Wallet Credited'),
        ('wallet_refunded', 'Wallet Refunded'),
    ]
    buyer = models.ForeignKey(
        Buyer,
        on_delete=models.CASCADE,
        related_name="notifications",
        blank=True,
        null=True,
    )
    seller = models.ForeignKey(
        Seller,
        on_delete=models.CASCADE,
        related_name="notifications",
        blank=True,
        null=True,
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="notifications",
        blank=True,
        null=True,
    )
    order_item = models.ForeignKey(
        OrderItem,
        on_delete=models.CASCADE,
        related_name="notifications",
        blank=True,
        null=True,
    )
    notification_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES)
    message = models.TextField()
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['buyer', 'is_read']),
            models.Index(fields=['seller', 'is_read']),
        ]

    def __str__(self):
        target = self.buyer or self.seller
        return f"Notification for {target} — {self.notification_type}"


class Wallet(models.Model):
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        # Check who owns this wallet via the reverse relation
        if hasattr(self, 'buyer_owner'):
            return f"Wallet of {self.buyer_owner.name} — ₹{self.balance}"
        if hasattr(self, 'seller_owner'):
            return f"Wallet of {self.seller_owner.name} — ₹{self.balance}"
        return f"Wallet #{self.id} — ₹{self.balance}"


class Transaction(models.Model):
    TRANSACTION_TYPES = [
        ('debit', 'Debit'),
        ('credit', 'Credit'),
        ('refund', 'Refund'),
        ('escrow_hold', 'Escrow Hold'),
        ('escrow_release', 'Escrow Release'),
        ('add_funds', 'Add Funds'),
    ]
    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.SET_NULL,
        related_name="transactions",
        blank=True,
        null=True,
    )
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Txn {self.transaction_type} ₹{self.amount} — {self.wallet}"
