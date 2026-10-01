import base64
import hashlib
import hmac
import json
from decimal import Decimal

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import Coupon, CustomerAddress, CustomerFavorite, Order, OrderItem, Product, ProductVariant


class StorefrontTests(TestCase):
	def setUp(self):
		self.product = Product.objects.create(
			name='Soft Day Shirt',
			slug='soft-day-shirt',
			category=Product.Category.TOPS,
			description='A relaxed shirt for every day.',
			price=Decimal('28.00'),
			image_url='https://example.com/shirt.jpg',
			image_alt='A white shirt',
			stock=10,
		)

	def test_catalog_and_product_detail_render(self):
		catalog = self.client.get(reverse('shop:home'))
		detail = self.client.get(reverse('shop:product_detail', args=[self.product.slug]))

		self.assertContains(catalog, 'Soft Day Shirt')
		self.assertContains(detail, 'A relaxed shirt for every day.')
		self.assertContains(detail, 'Style inspiration')
		self.assertEqual(len(detail.context['style_images']), 2)

	def test_checkout_renders_form_without_cart(self):
		response = self.client.get(reverse('shop:checkout'))

		self.assertContains(response, 'Street address')
		self.assertContains(response, 'Cambodia delivery')
		self.assertContains(response, 'Phnom Penh')

	def test_cart_add_requires_csrf_and_reports_count(self):
		client = Client(enforce_csrf_checks=True)
		client.get(reverse('shop:home'))
		csrf_token = client.cookies['csrftoken'].value

		response = client.post(
			reverse('shop:cart_change', args=[self.product.slug]),
			{'action': 'add', 'quantity': 1},
			HTTP_X_CSRFTOKEN=csrf_token,
			HTTP_X_REQUESTED_WITH='XMLHttpRequest',
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()['count'], 1)

	def test_cart_cannot_exceed_inventory(self):
		url = reverse('shop:cart_change', args=[self.product.slug])
		headers = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
		self.client.post(url, {'action': 'add', 'quantity': 1}, **headers)
		self.product.stock = 1
		self.product.save(update_fields=('stock',))

		response = self.client.post(url, {'action': 'add', 'quantity': 1}, **headers)

		self.assertEqual(response.status_code, 409)

	def test_legacy_cart_item_can_be_removed_after_variants_are_added(self):
		ProductVariant.objects.create(product=self.product, sku='TEST-LEGACY-S', size='S', color_name='Rose', stock=2)
		session = self.client.session
		session['cart'] = {str(self.product.pk): 1}
		session.save()
		response = self.client.post(
			reverse('shop:cart_change', args=[self.product.slug]),
			{'action': 'set', 'quantity': 0},
			HTTP_X_REQUESTED_WITH='XMLHttpRequest',
		)
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()['count'], 0)

	def test_checkout_persists_order_and_decrements_stock(self):
		session = self.client.session
		session['cart'] = {str(self.product.pk): 2}
		session.save()

		response = self.client.post(reverse('shop:checkout'), {
			'full_name': 'Jamie Example',
			'email': 'jamie@example.com',
			'phone': '+85512345678',
			'address': '12 Studio Lane',
			'district': 'Chamkar Mon',
			'city': 'Boeng Keng Kang',
			'province': 'Phnom Penh',
			'postal_code': '12000',
			'payment_method': 'cod',
			'coupon_code': '',
			'notes': '',
		})

		self.assertEqual(response.status_code, 302)
		confirmation = self.client.get(response['Location'])
		self.assertContains(confirmation, 'Good things are')
		self.assertContains(confirmation, 'In your order')
		self.assertContains(confirmation, '៛237,800')
		order = Order.objects.get()
		self.assertEqual(order.subtotal, Decimal('56.00'))
		self.assertEqual(order.shipping, Decimal('2.00'))
		self.assertEqual(order.total, Decimal('58.00'))
		self.assertEqual(OrderItem.objects.get(order=order).quantity, 2)
		self.product.refresh_from_db()
		self.assertEqual(self.product.stock, 8)
		self.assertNotIn('cart', self.client.session)

	def test_cambodian_phone_is_required(self):
		response = self.client.post(reverse('shop:checkout'), {
			'full_name': 'Jamie Example', 'email': 'jamie@example.com', 'phone': '555-0102',
			'address': '12 Studio Lane', 'city': 'BKK', 'province': 'Phnom Penh',
			'payment_method': 'cod',
		})
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Enter a Cambodian number')

	def test_signed_in_checkout_saves_default_address(self):
		from django.contrib.auth.models import User
		user = User.objects.create_user(username='address-customer', email='address@example.com', password='strong-password-5824')
		self.client.force_login(user)
		session = self.client.session
		session['cart'] = {str(self.product.pk): 1}
		session.save()
		response = self.client.post(reverse('shop:checkout'), {
			'full_name': 'Jamie Example', 'email': 'address@example.com', 'phone': '+85512345678',
			'address': '12 Studio Lane', 'district': 'Chamkar Mon', 'city': 'BKK', 'province': 'Phnom Penh',
			'postal_code': '12000', 'payment_method': 'cod', 'coupon_code': '', 'save_address': 'on',
		})
		self.assertEqual(response.status_code, 302)
		address = CustomerAddress.objects.get(user=user)
		self.assertTrue(address.is_default)
		self.assertContains(self.client.get(reverse('shop:account')), 'Chamkar Mon')

	def test_variant_cart_and_order_preserve_size_and_color(self):
		variant = ProductVariant.objects.create(
			product=self.product, sku='TEST-S-ROSE', size='S', color_name='Rose', color_hex='#F29FA0', stock=2,
		)
		response = self.client.post(
			reverse('shop:cart_change', args=[self.product.slug]),
			{'action': 'add', 'quantity': 1, 'variant_id': variant.pk},
			HTTP_X_REQUESTED_WITH='XMLHttpRequest',
		)
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()['items'][0]['variant_label'], 'S / Rose')
		self.client.session.flush()
		response = self.client.post(
			reverse('shop:cart_change', args=[self.product.slug]),
			{'action': 'add', 'quantity': 1, 'variant': variant.pk},
		)
		self.assertEqual(response.status_code, 302)
		self.assertEqual(self.client.session['cart'][f'v:{variant.pk}'], 1)
		session = self.client.session
		session['cart'] = {f'v:{variant.pk}': 1}
		session.save()
		response = self.client.post(reverse('shop:checkout'), {
			'full_name': 'Jamie Example', 'email': 'jamie@example.com', 'phone': '+85512345678',
			'address': '12 Studio Lane', 'district': 'Chamkar Mon', 'city': 'BKK',
			'province': 'Phnom Penh', 'postal_code': '', 'payment_method': 'cod', 'coupon_code': '',
		})
		self.assertEqual(response.status_code, 302)
		item = OrderItem.objects.get()
		self.assertEqual(item.selected_size, 'S')
		self.assertEqual(item.selected_color, 'Rose')
		variant.refresh_from_db()
		self.assertEqual(variant.stock, 1)

	def test_coupon_discount_is_applied_to_order(self):
		Coupon.objects.create(code='SWEET10', discount_type=Coupon.DiscountType.PERCENT, amount=Decimal('10'))
		session = self.client.session
		session['cart'] = {str(self.product.pk): 2}
		session.save()
		response = self.client.post(reverse('shop:checkout'), {
			'full_name': 'Jamie Example', 'email': 'jamie@example.com', 'phone': '+85512345678',
			'address': '12 Studio Lane', 'district': '', 'city': 'Phnom Penh', 'province': 'Phnom Penh',
			'postal_code': '', 'payment_method': 'cod', 'coupon_code': 'sweet10',
		})
		self.assertEqual(response.status_code, 302)
		order = Order.objects.get()
		self.assertEqual(order.discount, Decimal('5.60'))
		self.assertEqual(order.total, Decimal('52.40'))
		self.assertEqual(Coupon.objects.get().uses, 1)

	def test_customer_registration_and_favorites(self):
		response = self.client.post(reverse('shop:register'), {
			'first_name': 'Jamie', 'last_name': 'Example', 'username': 'jamie',
			'email': 'jamie@example.com', 'password1': 'safepassword-4821',
			'password2': 'safepassword-4821',
		})
		self.assertEqual(response.status_code, 302)
		self.assertTrue('_auth_user_id' in self.client.session)
		response = self.client.post(
			reverse('shop:favorite_toggle', args=[self.product.slug]),
			HTTP_X_REQUESTED_WITH='XMLHttpRequest',
		)
		self.assertTrue(response.json()['favorite'])
		self.assertTrue(CustomerFavorite.objects.filter(product=self.product).exists())
		self.assertEqual(self.client.get(reverse('shop:account')).status_code, 200)

	def test_cambodia_policy_and_contact_pages_render(self):
		self.assertContains(self.client.get(reverse('shop:policy', args=['shipping'])), 'Phnom Penh delivery')
		self.assertContains(self.client.get(reverse('shop:policy', args=['privacy'])), 'Privacy notice')
		self.assertContains(self.client.get(reverse('shop:contact')), 'Phnom Penh, Cambodia')

	@override_settings(PAYWAY_MERCHANT_ID='sandbox-merchant', PAYWAY_API_KEY='sandbox-api-key')
	def test_payway_checkout_form_contains_signed_request_fields(self):
		order = Order.objects.create(
			transaction_id='payway-test-123', payment_method=Order.PaymentMethod.PAYWAY,
			full_name='Jamie Example', email='jamie@example.com', phone='+85512345678',
			address='12 Studio Lane', city='Phnom Penh', province='Phnom Penh',
			subtotal=Decimal('28.00'), shipping=Decimal('2.00'), total=Decimal('30.00'),
		)
		OrderItem.objects.create(order=order, product=self.product, product_name=self.product.name, unit_price=self.product.price, quantity=1)

		response = self.client.get(reverse('shop:payway_redirect', args=[order.public_id]))

		self.assertContains(response, 'name="merchant_id"')
		self.assertContains(response, 'name="hash"')
		self.assertContains(response, 'action="https://checkout-sandbox.payway.com.kh/api/payment-gateway/v1/payments/purchase"')

	@override_settings(PAYWAY_API_KEY='test-payway-key')
	def test_invalid_payway_callback_cannot_mark_order_paid(self):
		order = Order.objects.create(
			transaction_id='test-transaction', payment_method=Order.PaymentMethod.PAYWAY,
			full_name='Jamie Example', email='jamie@example.com', phone='+85512345678',
			address='12 Studio Lane', city='Phnom Penh', province='Phnom Penh',
			subtotal=Decimal('28.00'), shipping=Decimal('2.00'), total=Decimal('30.00'),
		)
		payload = json.dumps({'tran_id': order.transaction_id, 'status': '0'})
		response = self.client.post(reverse('shop:payway_callback'), payload, content_type='application/json', HTTP_X_PAYWAY_HMAC_SHA512='invalid')
		self.assertEqual(response.status_code, 401)
		order.refresh_from_db()
		self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)

	@override_settings(PAYWAY_API_KEY='test-payway-key')
	def test_failed_payway_callback_releases_variant_stock(self):
		variant = ProductVariant.objects.create(product=self.product, sku='TEST-M-INK', size='M', color_name='Ink', stock=4)
		order = Order.objects.create(
			transaction_id='test-failed', payment_method=Order.PaymentMethod.PAYWAY,
			full_name='Jamie Example', email='jamie@example.com', phone='+85512345678',
			address='12 Studio Lane', city='Phnom Penh', province='Phnom Penh',
			subtotal=Decimal('28.00'), shipping=Decimal('2.00'), total=Decimal('30.00'),
		)
		OrderItem.objects.create(order=order, product=self.product, variant=variant, product_name=self.product.name, selected_size='M', selected_color='Ink', unit_price=self.product.price, quantity=1)
		data = {'tran_id': order.transaction_id, 'status': '201'}
		body = json.dumps(data)
		canonical = ''.join(str(data[key]) for key in sorted(data))
		signature = base64.b64encode(hmac.new(b'test-payway-key', canonical.encode(), hashlib.sha512).digest()).decode()
		response = self.client.post(reverse('shop:payway_callback'), body, content_type='application/json', HTTP_X_PAYWAY_HMAC_SHA512=signature)
		self.assertEqual(response.status_code, 200)
		order.refresh_from_db()
		variant.refresh_from_db()
		self.assertEqual(order.payment_status, Order.PaymentStatus.FAILED)
		self.assertEqual(order.status, Order.Status.CANCELLED)
		self.assertEqual(variant.stock, 5)

	@override_settings(PAYWAY_API_KEY='test-payway-key')
	def test_successful_payway_callback_requires_matching_signed_total(self):
		order = Order.objects.create(
			transaction_id='test-paid', payment_method=Order.PaymentMethod.PAYWAY,
			full_name='Jamie Example', email='jamie@example.com', phone='+85512345678',
			address='12 Studio Lane', city='Phnom Penh', province='Phnom Penh',
			subtotal=Decimal('28.00'), shipping=Decimal('2.00'), total=Decimal('30.00'),
		)
		data = {'tran_id': order.transaction_id, 'status': '0', 'total_amount': '29.00', 'original_currency': 'USD'}
		body = json.dumps(data)
		canonical = ''.join(str(data[key]) for key in sorted(data))
		signature = base64.b64encode(hmac.new(b'test-payway-key', canonical.encode(), hashlib.sha512).digest()).decode()
		response = self.client.post(reverse('shop:payway_callback'), body, content_type='application/json', HTTP_X_PAYWAY_HMAC_SHA512=signature)
		self.assertEqual(response.status_code, 200)
		order.refresh_from_db()
		self.assertEqual(order.payment_status, Order.PaymentStatus.FAILED)
		self.assertEqual(order.status, Order.Status.CANCELLED)

	@override_settings(PAYWAY_API_KEY='test-payway-key')
	def test_matching_payway_callback_marks_order_paid(self):
		order = Order.objects.create(
			transaction_id='test-paid-valid', payment_method=Order.PaymentMethod.PAYWAY,
			full_name='Jamie Example', email='jamie@example.com', phone='+85512345678',
			address='12 Studio Lane', city='Phnom Penh', province='Phnom Penh',
			subtotal=Decimal('28.00'), shipping=Decimal('2.00'), total=Decimal('30.00'),
		)
		data = {'tran_id': order.transaction_id, 'status': '0', 'total_amount': '30.00', 'original_currency': 'USD'}
		body = json.dumps(data)
		canonical = ''.join(str(data[key]) for key in sorted(data))
		signature = base64.b64encode(hmac.new(b'test-payway-key', canonical.encode(), hashlib.sha512).digest()).decode()
		response = self.client.post(reverse('shop:payway_callback'), body, content_type='application/json', HTTP_X_PAYWAY_HMAC_SHA512=signature)
		self.assertEqual(response.status_code, 200)
		order.refresh_from_db()
		self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
		self.assertEqual(order.status, Order.Status.PROCESSING)
