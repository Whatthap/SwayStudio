import uuid

from django.db import models


class Product(models.Model):
	class Category(models.TextChoices):
		TOPS = 'tops', 'Tops'
		DRESSES = 'dresses', 'Dresses'
		BOTTOMS = 'bottoms', 'Bottoms'
		OUTERWEAR = 'outerwear', 'Outerwear'
		ACCESSORIES = 'accessories', 'Accessories'

	name = models.CharField(max_length=120)
	slug = models.SlugField(unique=True)
	category = models.CharField(max_length=20, choices=Category.choices)
	description = models.TextField()
	price = models.DecimalField(max_digits=8, decimal_places=2)
	image_url = models.CharField(max_length=500)
	image_alt = models.CharField(max_length=180)
	badge = models.CharField(max_length=40, blank=True)
	featured = models.BooleanField(default=False)
	active = models.BooleanField(default=True)
	stock = models.PositiveIntegerField(default=20)

	class Meta:
		ordering = ('-featured', 'name')

	def __str__(self):
		return self.name

	@property
	def has_variants(self):
		return self.variants.exists()


class ProductVariant(models.Model):
	product = models.ForeignKey(Product, related_name='variants', on_delete=models.CASCADE)
	sku = models.CharField(max_length=40, unique=True)
	size = models.CharField(max_length=20)
	color_name = models.CharField(max_length=40)
	color_hex = models.CharField(max_length=7, default='#F29FA0')
	stock = models.PositiveIntegerField(default=0)

	class Meta:
		ordering = ('size', 'color_name')
		constraints = [models.UniqueConstraint(fields=('product', 'size', 'color_name'), name='unique_product_size_color')]

	def __str__(self):
		return f'{self.product.name} / {self.size} / {self.color_name}'


class Order(models.Model):
	class Status(models.TextChoices):
		NEW = 'new', 'New'
		PROCESSING = 'processing', 'Processing'
		SHIPPED = 'shipped', 'Shipped'
		COMPLETE = 'complete', 'Complete'
		CANCELLED = 'cancelled', 'Cancelled'

	class PaymentMethod(models.TextChoices):
		COD = 'cod', 'Cash on delivery'
		PAYWAY = 'payway', 'ABA PayWay'

	class PaymentStatus(models.TextChoices):
		PENDING = 'pending', 'Pending'
		PAID = 'paid', 'Paid'
		FAILED = 'failed', 'Failed'

	public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
	transaction_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
	user = models.ForeignKey('auth.User', null=True, blank=True, related_name='shop_orders', on_delete=models.SET_NULL)
	full_name = models.CharField(max_length=120)
	email = models.EmailField()
	phone = models.CharField(max_length=30)
	address = models.CharField(max_length=200)
	city = models.CharField(max_length=100)
	province = models.CharField(max_length=100, default='Phnom Penh')
	district = models.CharField(max_length=100, blank=True)
	postal_code = models.CharField(max_length=20, blank=True)
	notes = models.TextField(blank=True)
	subtotal = models.DecimalField(max_digits=9, decimal_places=2)
	shipping = models.DecimalField(max_digits=7, decimal_places=2)
	discount = models.DecimalField(max_digits=7, decimal_places=2, default=0)
	coupon_code = models.CharField(max_length=40, blank=True)
	total = models.DecimalField(max_digits=9, decimal_places=2)
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
	payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.COD)
	payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ('-created_at',)

	def __str__(self):
		return f'Order {self.public_id}'

	@property
	def formatted_delivery_address(self):
		parts = [self.address, self.district, self.city, self.province, self.postal_code]
		return ', '.join(part for part in parts if part)


class OrderItem(models.Model):
	order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
	product = models.ForeignKey(Product, on_delete=models.PROTECT)
	variant = models.ForeignKey(ProductVariant, null=True, blank=True, on_delete=models.PROTECT)
	product_name = models.CharField(max_length=120)
	selected_size = models.CharField(max_length=20, blank=True)
	selected_color = models.CharField(max_length=40, blank=True)
	unit_price = models.DecimalField(max_digits=8, decimal_places=2)
	quantity = models.PositiveIntegerField()

	@property
	def line_total(self):
		return self.unit_price * self.quantity

	@property
	def variant_label(self):
		return f'{self.selected_size} · {self.selected_color}' if self.selected_size else ''


class Coupon(models.Model):
	class DiscountType(models.TextChoices):
		PERCENT = 'percent', 'Percentage'
		FIXED = 'fixed', 'Fixed USD amount'

	code = models.CharField(max_length=40, unique=True)
	discount_type = models.CharField(max_length=10, choices=DiscountType.choices)
	amount = models.DecimalField(max_digits=7, decimal_places=2)
	active = models.BooleanField(default=True)
	starts_at = models.DateTimeField(null=True, blank=True)
	expires_at = models.DateTimeField(null=True, blank=True)
	maximum_uses = models.PositiveIntegerField(null=True, blank=True)
	uses = models.PositiveIntegerField(default=0)

	def __str__(self):
		return self.code


class Review(models.Model):
	product = models.ForeignKey(Product, related_name='reviews', on_delete=models.CASCADE)
	user = models.ForeignKey('auth.User', related_name='shop_reviews', on_delete=models.CASCADE)
	rating = models.PositiveSmallIntegerField()
	body = models.TextField(max_length=1000)
	approved = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ('-created_at',)
		constraints = [
			models.UniqueConstraint(fields=('product', 'user'), name='one_review_per_customer_product'),
			models.CheckConstraint(check=models.Q(rating__gte=1, rating__lte=5), name='review_rating_1_to_5'),
		]


class CustomerFavorite(models.Model):
	user = models.ForeignKey('auth.User', related_name='shop_favorites', on_delete=models.CASCADE)
	product = models.ForeignKey(Product, related_name='favorited_by', on_delete=models.CASCADE)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		constraints = [models.UniqueConstraint(fields=('user', 'product'), name='one_favorite_per_customer_product')]


class CustomerAddress(models.Model):
	user = models.ForeignKey('auth.User', related_name='shop_addresses', on_delete=models.CASCADE)
	label = models.CharField(max_length=40, default='Home')
	full_name = models.CharField(max_length=120)
	phone = models.CharField(max_length=30)
	address = models.CharField(max_length=200)
	district = models.CharField(max_length=100, blank=True)
	city = models.CharField(max_length=100)
	province = models.CharField(max_length=100)
	postal_code = models.CharField(max_length=20, blank=True)
	is_default = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ('-is_default', '-created_at')
		constraints = [
			models.UniqueConstraint(fields=('user',), condition=models.Q(is_default=True), name='one_default_address_per_customer'),
		]

	def __str__(self):
		return f'{self.label} · {self.province}'

	@property
	def display_label(self):
		return f'{self.label} · Default' if self.is_default else self.label

	@property
	def formatted_address(self):
		parts = [self.address]
		if self.district:
			parts.append(self.district)
		parts.extend((self.city, self.province, self.postal_code))
		return ', '.join(part for part in parts if part)
