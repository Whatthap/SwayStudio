from django.contrib import admin

from .models import Coupon, Order, OrderItem, Product, ProductVariant, Review


class ProductVariantInline(admin.TabularInline):
	model = ProductVariant
	extra = 0
	fields = ('sku', 'size', 'color_name', 'color_hex', 'stock')


class LowStockFilter(admin.SimpleListFilter):
	title = 'stock level'
	parameter_name = 'stock_level'

	def lookups(self, request, model_admin):
		return (('low', 'Low: 1-5 left'), ('empty', 'Out of stock'))

	def queryset(self, request, queryset):
		if self.value() == 'low':
			return queryset.filter(stock__gt=0, stock__lte=5)
		if self.value() == 'empty':
			return queryset.filter(stock=0)
		return queryset


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
	list_display = ('name', 'category', 'price', 'stock', 'active', 'featured')
	list_filter = ('category', 'active', 'featured')
	search_fields = ('name', 'description')
	prepopulated_fields = {'slug': ('name',)}
	inlines = (ProductVariantInline,)


class OrderItemInline(admin.TabularInline):
	model = OrderItem
	extra = 0
	readonly_fields = ('product', 'product_name', 'unit_price', 'quantity')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
	list_display = ('public_id', 'full_name', 'province', 'total', 'payment_method', 'payment_status', 'status', 'created_at')
	list_filter = ('status', 'payment_method', 'payment_status', 'province', 'created_at')
	search_fields = ('public_id', 'transaction_id', 'full_name', 'email', 'phone')
	readonly_fields = ('public_id', 'created_at')
	inlines = (OrderItemInline,)
	actions = ('mark_processing', 'mark_shipped', 'mark_complete')

	@admin.action(description='Mark selected orders as processing')
	def mark_processing(self, request, queryset):
		queryset.update(status=Order.Status.PROCESSING)

	@admin.action(description='Mark selected orders as shipped')
	def mark_shipped(self, request, queryset):
		queryset.update(status=Order.Status.SHIPPED)

	@admin.action(description='Mark selected orders as complete')
	def mark_complete(self, request, queryset):
		queryset.update(status=Order.Status.COMPLETE)


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
	list_display = ('code', 'discount_type', 'amount', 'active', 'uses', 'maximum_uses', 'expires_at')
	list_filter = ('active', 'discount_type')
	search_fields = ('code',)


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
	list_display = ('product', 'user', 'rating', 'approved', 'created_at')
	list_filter = ('approved', 'rating', 'created_at')
	search_fields = ('product__name', 'user__username', 'body')


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
	list_display = ('sku', 'product', 'size', 'color_name', 'stock')
	list_filter = ('size', 'color_name', 'product__category', LowStockFilter)
	search_fields = ('sku', 'product__name', 'color_name')


