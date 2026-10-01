import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone as datetime_timezone
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.db import models, transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .forms import CheckoutForm, CustomerRegistrationForm, ReviewForm, VariantForm
from .models import Coupon, CustomerAddress, CustomerFavorite, Order, OrderItem, Product, ProductVariant, Review


FREE_SHIPPING_THRESHOLD = Decimal('100.00')
PHNOM_PENH_SHIPPING = Decimal(settings.CAMBODIA_SHIPPING_PHNOM_PENH)
PROVINCE_SHIPPING = Decimal(settings.CAMBODIA_SHIPPING_PROVINCES)
KHR_PER_USD = Decimal(getattr(settings, 'CAMBODIA_KHR_PER_USD', '4100'))

STYLE_INSPIRATION = {
	'boys': (
		{
			'image': 'shop/inspiration/men-urban.jpg',
			'alt': 'Two young men in relaxed streetwear on a city bench',
			'credit': 'Photo by Leospa · Pexels',
			'source': 'https://www.pexels.com/photo/two-young-men-in-beanie-hats-posing-on-a-bench-18095049/',
		},
		{
			'image': 'shop/inspiration/men-skate.jpg',
			'alt': 'Streetwear look with a hoodie and skateboard',
			'credit': 'Photo by Syed Ahamed Nadim · Pexels',
			'source': 'https://www.pexels.com/photo/man-standing-with-skateboard-on-basketball-court-10243583/',
		},
		{
			'image': 'shop/inspiration/couple-skate.jpg',
			'alt': 'Young friends wearing colorful casual streetwear with skateboards',
			'credit': 'Photo by Antoni Shkraba · Pexels',
			'source': 'https://www.pexels.com/photo/man-holding-skateboard-while-embracing-a-woman-7081107/',
		},
	),
	'girls': (
		{
			'image': 'shop/inspiration/women-skate.jpg',
			'alt': 'Two women skateboarding in relaxed streetwear',
			'credit': 'Photo by Yaroslav Shuraev · Pexels',
			'source': 'https://www.pexels.com/photo/women-riding-skateboards-at-the-skatepark-7634778/',
		},
		{
			'image': 'shop/inspiration/women-city.jpg',
			'alt': 'Two friends in casual city outfits',
			'credit': 'Photo by Aksio Art · Pexels',
			'source': 'https://www.pexels.com/photo/two-young-women-in-jackets-standing-on-a-sidewalk-and-smiling-19273128/',
		},
		{
			'image': 'shop/inspiration/group-graffiti.jpg',
			'alt': 'Young friends in colorful streetwear beside a graffiti wall',
			'credit': 'Photo by Anthony Shkraba · Pexels',
			'source': 'https://www.pexels.com/photo/trendy-young-man-and-women-standing-on-the-background-of-a-graffiti-wall-8973475/',
		},
	),
}


def khr_amount(amount):
	return int((Decimal(amount) * KHR_PER_USD).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def _shipping(province, subtotal):
	if not subtotal or subtotal >= FREE_SHIPPING_THRESHOLD:
		return Decimal('0.00')
	return PHNOM_PENH_SHIPPING if province == 'Phnom Penh' else PROVINCE_SHIPPING


def _read_cart(request):
	cart = request.session.get('cart', {})
	if not isinstance(cart, dict):
		return {}
	normalized = {}
	for key, quantity in cart.items():
		if isinstance(key, str) and not key.startswith(('p:', 'v:')):
			try:
				key = f'p:{int(key)}'
			except ValueError:
				continue
		normalized[key] = quantity
	return normalized


def _cart_payload(request, province='Phnom Penh'):
	cart = _read_cart(request)
	items = []
	subtotal = Decimal('0.00')
	for cart_key, raw_quantity in cart.items():
		try:
			quantity = int(raw_quantity)
			if quantity < 1:
				continue
			if cart_key.startswith('v:'):
				variant = ProductVariant.objects.select_related('product').filter(pk=int(cart_key[2:]), product__active=True).first()
				if not variant:
					continue
				product = variant.product
				stock = variant.stock
				variant_id = variant.pk
				selected_size = variant.size
				selected_color = variant.color_name
				variant_label = f'{selected_size} / {selected_color}'
			else:
				product_id = int(cart_key[2:]) if cart_key.startswith('p:') else int(cart_key)
				product = Product.objects.filter(pk=product_id, active=True).first()
				if not product:
					continue
				stock = product.stock
				variant_id = None
				selected_size = ''
				selected_color = ''
				variant_label = ''
			displayed_quantity = min(quantity, stock)
			if not displayed_quantity:
				continue
		except (TypeError, ValueError):
			continue
		line_total = product.price * displayed_quantity
		subtotal += line_total
		items.append({
			'id': product.pk,
			'slug': product.slug,
			'key': cart_key,
			'name': product.name,
			'price': str(product.price),
			'price_khr': khr_amount(product.price),
			'image_url': product.image_url,
			'quantity': displayed_quantity,
			'line_total': str(line_total),
			'line_total_khr': khr_amount(line_total),
			'stock': stock,
			'variant_id': variant_id,
			'size': selected_size,
			'color': selected_color,
			'variant_label': variant_label,
		})
	shipping = _shipping(province, subtotal)
	return {
		'items': items,
		'count': sum(item['quantity'] for item in items),
		'subtotal': str(subtotal),
		'subtotal_khr': khr_amount(subtotal),
		'shipping': str(shipping),
		'shipping_khr': khr_amount(shipping),
		'shipping_label': '—' if not subtotal else ('Free' if not shipping else f'${shipping:.2f}'),
		'total': str(subtotal + shipping),
		'total_khr': khr_amount(subtotal + shipping),
		'free_shipping_threshold': str(FREE_SHIPPING_THRESHOLD),
		'khr_per_usd': str(KHR_PER_USD),
		'province': province,
	}


def home(request):
	products = Product.objects.filter(active=True).prefetch_related('variants')
	category = request.GET.get('category', '')
	query = request.GET.get('q', '').strip()
	sort = request.GET.get('sort', 'featured')
	if category in Product.Category.values:
		products = products.filter(category=category)
	else:
		category = ''
	if query:
		products = products.filter(name__icontains=query) | products.filter(description__icontains=query)
	if sort == 'price-low':
		products = products.order_by('price', 'name')
	elif sort == 'price-high':
		products = products.order_by('-price', 'name')
	elif sort == 'newest':
		products = products.order_by('-pk')
	else:
		sort = 'featured'
	return render(request, 'shop/home.html', {
		'products': products,
		'categories': Product.Category.choices,
		'selected_category': category,
		'query': query,
		'sort': sort,
		'cart': _cart_payload(request),
		'is_authenticated': request.user.is_authenticated,
		'favorite_slugs': list(CustomerFavorite.objects.filter(user=request.user).values_list('product__slug', flat=True)) if request.user.is_authenticated else [],
	})


def product_detail(request, slug):
	product = get_object_or_404(Product.objects.prefetch_related('variants', 'reviews__user'), slug=slug, active=True)
	style_images = STYLE_INSPIRATION['boys' if product.slug.startswith('boys-') else 'girls']
	image_start = product.pk % len(style_images)
	style_images = style_images[image_start:] + style_images[:image_start]
	review_form = ReviewForm()
	if request.method == 'POST':
		if not request.user.is_authenticated:
			return redirect(f'{reverse("shop:login")}?next={request.path}')
		if Review.objects.filter(product=product, user=request.user).exists():
			messages.info(request, 'You have already reviewed this piece.')
		else:
			review_form = ReviewForm(request.POST)
			if review_form.is_valid():
				review = review_form.save(commit=False)
				review.product = product
				review.user = request.user
				review.save()
				messages.success(request, 'Thanks. Your review will appear after moderation.')
				return redirect('shop:product_detail', slug=slug)
			messages.error(request, 'Please check your review and try again.')
	return render(request, 'shop/product_detail.html', {
		'product': product,
		'style_images': style_images[:2],
		'category_label': product.get_category_display(),
		'has_variants': product.variants.exists(),
		'has_available_variants': VariantForm(product).fields['variant'].queryset.exists(),
		'can_add_legacy_product': not product.variants.exists() and product.stock > 0,
		'legacy_product_sold_out': not product.variants.exists() and product.stock == 0,
		'related_products': Product.objects.filter(active=True, category=product.category).exclude(pk=product.pk).prefetch_related('variants')[:3],
		'cart': _cart_payload(request),
		'variant_form': VariantForm(product),
		'review_form': review_form,
		'reviews': product.reviews.filter(approved=True),
		'average_rating': product.reviews.filter(approved=True).aggregate(models.Avg('rating'))['rating__avg'],
		'is_favorite': request.user.is_authenticated and CustomerFavorite.objects.filter(user=request.user, product=product).exists(),
		'favorite_label': '♥ Saved to your pieces' if request.user.is_authenticated and CustomerFavorite.objects.filter(user=request.user, product=product).exists() else '♡ Save this piece',
		'has_reviewed': request.user.is_authenticated and Review.objects.filter(user=request.user, product=product).exists(),
		'can_review': request.user.is_authenticated and not Review.objects.filter(user=request.user, product=product).exists(),
		'show_review_signin': not request.user.is_authenticated,
	})


@require_POST
def cart_change(request, slug):
	product = get_object_or_404(Product, slug=slug, active=True)
	cart = _read_cart(request)
	action = request.POST.get('action', 'add')
	variant_id = (request.POST.get('variant_id') or request.POST.get('variant', '')).strip()
	variant = None
	if variant_id:
		variant = get_object_or_404(ProductVariant, pk=variant_id, product=product)
		key = f'v:{variant.pk}'
		stock = variant.stock
	elif product.variants.exists() and not (action == 'set' and f'p:{product.pk}' in cart):
		return JsonResponse({'ok': False, 'error': 'Choose a size and color first.'}, status=400)
	else:
		key = f'p:{product.pk}'
		stock = product.stock
	try:
		quantity = int(request.POST.get('quantity', 1))
		current = int(cart.get(key, 0))
	except (TypeError, ValueError):
		return JsonResponse({'ok': False, 'error': 'Choose a valid quantity.'}, status=400)
	if action == 'add':
		quantity = current + 1
	elif action != 'set':
		return JsonResponse({'ok': False, 'error': 'That cart action is not available.'}, status=400)
	if quantity > stock:
		return JsonResponse({'ok': False, 'error': 'There are not enough pieces in that size and color.'}, status=409)
	if quantity <= 0:
		cart.pop(key, None)
	else:
		cart[key] = quantity
	request.session['cart'] = cart
	if request.headers.get('x-requested-with') == 'XMLHttpRequest':
		return JsonResponse({'ok': True, **_cart_payload(request)})
	return redirect('shop:product_detail', slug=slug)


def _coupon_discount(code, subtotal, lock=False):
	if not code:
		return None, Decimal('0.00')
	query = Coupon.objects
	if lock:
		query = query.select_for_update()
	coupon = query.filter(code__iexact=code, active=True).first()
	if not coupon:
		return None, Decimal('0.00')
	now = timezone.now()
	if coupon.starts_at and coupon.starts_at > now:
		return None, Decimal('0.00')
	if coupon.expires_at and coupon.expires_at < now:
		return None, Decimal('0.00')
	if coupon.maximum_uses is not None and coupon.uses >= coupon.maximum_uses:
		return None, Decimal('0.00')
	if coupon.discount_type == Coupon.DiscountType.PERCENT:
		discount = min((subtotal * coupon.amount / Decimal('100')).quantize(Decimal('0.01')), subtotal)
	else:
		discount = min(coupon.amount, subtotal)
	return coupon, discount


def checkout(request):
	province = request.POST.get('province') or request.GET.get('province') or 'Phnom Penh'
	cart = _cart_payload(request, province)
	form = CheckoutForm(request.POST or None, user=request.user)
	if request.method == 'POST':
		if not cart['items']:
			form.add_error(None, 'Your bag is empty. Add something lovely first.')
		elif form.is_valid():
			try:
				with transaction.atomic():
					product_ids = [item['id'] for item in cart['items']]
					products = {product.pk: product for product in Product.objects.select_for_update().filter(pk__in=product_ids, active=True)}
					variants = {variant.pk: variant for variant in ProductVariant.objects.select_for_update().filter(pk__in=[item['variant_id'] for item in cart['items'] if item['variant_id']])}
					if len(products) != len({item['id'] for item in cart['items']}):
						raise ValueError('One of your items is no longer available.')
					for item in cart['items']:
						stock = variants[item['variant_id']].stock if item['variant_id'] else products[item['id']].stock
						if not item['variant_id'] and products[item['id']].variants.exists():
							raise ValueError(f'Choose a size and color for {item["name"]} before checkout.')
						if stock < item['quantity']:
							raise ValueError(f'{item["name"]} no longer has that many in stock.')
					subtotal = sum((products[item['id']].price * item['quantity'] for item in cart['items']), Decimal('0.00'))
					coupon, discount = _coupon_discount(form.cleaned_data['coupon_code'], subtotal, lock=True)
					if form.cleaned_data['coupon_code'] and not coupon:
						form.add_error('coupon_code', 'That code is invalid, expired, or has reached its use limit.')
						raise ValueError('coupon')
					shipping = _shipping(form.cleaned_data['province'], subtotal - discount)
					payment_method = form.cleaned_data['payment_method']
					if payment_method == Order.PaymentMethod.PAYWAY and not (settings.PAYWAY_MERCHANT_ID and settings.PAYWAY_API_KEY):
						raise ValueError('ABA PayWay is not configured yet. Please choose cash on delivery.')
					order = Order.objects.create(
						user=request.user if request.user.is_authenticated else None,
						full_name=form.cleaned_data['full_name'], email=form.cleaned_data['email'], phone=form.cleaned_data['phone'],
						address=form.cleaned_data['address'], district=form.cleaned_data['district'], city=form.cleaned_data['city'],
						province=form.cleaned_data['province'], postal_code=form.cleaned_data['postal_code'], notes=form.cleaned_data['notes'],
						subtotal=subtotal, shipping=shipping, discount=discount, coupon_code=coupon.code if coupon else '',
						total=subtotal - discount + shipping, payment_method=payment_method,
						transaction_id=secrets.token_hex(10) if payment_method == Order.PaymentMethod.PAYWAY else None,
					)
					for item in cart['items']:
						product = products[item['id']]
						variant = variants.get(item['variant_id'])
						OrderItem.objects.create(
							order=order, product=product, variant=variant, product_name=product.name,
							selected_size=variant.size if variant else '', selected_color=variant.color_name if variant else '',
							unit_price=product.price, quantity=item['quantity'],
						)
						if variant:
							variant.stock -= item['quantity']
							variant.save(update_fields=('stock',))
						else:
							product.stock -= item['quantity']
							product.save(update_fields=('stock',))
					if coupon:
						coupon.uses += 1
						coupon.save(update_fields=('uses',))
					if request.user.is_authenticated and form.cleaned_data['save_address']:
						has_saved_address = CustomerAddress.objects.filter(user=request.user).exists()
						CustomerAddress.objects.get_or_create(
							user=request.user, full_name=form.cleaned_data['full_name'], phone=form.cleaned_data['phone'],
							address=form.cleaned_data['address'], district=form.cleaned_data['district'],
							city=form.cleaned_data['city'], province=form.cleaned_data['province'],
							postal_code=form.cleaned_data['postal_code'],
							defaults={'label': 'Home', 'is_default': not has_saved_address},
						)
			except ValueError as error:
				if str(error) != 'coupon':
					form.add_error(None, str(error))
			else:
				request.session.pop('cart', None)
				if order.payment_method == Order.PaymentMethod.PAYWAY:
					return redirect('shop:payway_redirect', public_id=order.public_id)
				return redirect('shop:order_success', public_id=order.public_id)
	return render(request, 'shop/checkout.html', {
		'form': form, 'cart': cart, 'province_choices': CheckoutForm.base_fields['province'].choices,
		'payway_ready': bool(settings.PAYWAY_MERCHANT_ID and settings.PAYWAY_API_KEY),
		'coupon_preview': _coupon_discount(request.GET.get('coupon', ''), Decimal(cart['subtotal']))[1],
	})


def payway_redirect(request, public_id):
	order = get_object_or_404(Order, public_id=public_id, payment_method=Order.PaymentMethod.PAYWAY)
	if not settings.PAYWAY_MERCHANT_ID or not settings.PAYWAY_API_KEY:
		return redirect('shop:order_success', public_id=order.public_id)
	callback_url = request.build_absolute_uri(reverse('shop:payway_callback'))
	return_url = base64.b64encode(callback_url.encode()).decode()
	continue_url = request.build_absolute_uri(reverse('shop:order_success', args=[order.public_id]))
	name_parts = order.full_name.strip().split(' ', 1)
	items = [
		{'name': f'{item.product_name} {item.selected_size} {item.selected_color}'.strip(), 'quantity': item.quantity, 'price': float(item.unit_price)}
		for item in order.items.all()
	]
	encoded_items = base64.b64encode(json.dumps(items, separators=(',', ':')).encode()).decode()
	payload = {
		'req_time': datetime.now(datetime_timezone.utc).strftime('%Y%m%d%H%M%S'),
		'merchant_id': settings.PAYWAY_MERCHANT_ID,
		'tran_id': order.transaction_id,
		'amount': f'{order.subtotal - order.discount:.2f}',
		'items': encoded_items,
		'shipping': f'{order.shipping:.2f}',
		'firstname': name_parts[0][:100],
		'lastname': name_parts[1][:100] if len(name_parts) > 1 else '',
		'email': order.email,
		'phone': order.phone,
		'type': 'purchase',
		'payment_option': '',
		'return_url': return_url,
		'cancel_url': '',
		'continue_success_url': continue_url,
		'return_deeplink': '',
		'currency': 'USD',
		'custom_fields': '',
		'return_params': '',
		'payout': '',
		'lifetime': '30',
		'additional_params': '',
		'google_pay_token': '',
		'skip_success_page': '0',
	}
	order_fields = ('req_time', 'merchant_id', 'tran_id', 'amount', 'items', 'shipping', 'firstname', 'lastname', 'email', 'phone', 'type', 'payment_option', 'return_url', 'cancel_url', 'continue_success_url', 'return_deeplink', 'currency', 'custom_fields', 'return_params', 'payout', 'lifetime', 'additional_params', 'google_pay_token', 'skip_success_page')
	message = ''.join(payload[field] for field in order_fields)
	payload['hash'] = base64.b64encode(hmac.new(settings.PAYWAY_API_KEY.encode(), message.encode(), hashlib.sha512).digest()).decode()
	return render(request, 'shop/payway_redirect.html', {
		'payway_url': settings.PAYWAY_BASE_URL.rstrip('/') + '/api/payment-gateway/v1/payments/purchase',
		'payload': payload,
		'fields': payload.items(),
	})


@csrf_exempt
@require_POST
def payway_callback(request):
	try:
		data = json.loads(request.body.decode())
	except (json.JSONDecodeError, UnicodeDecodeError):
		return HttpResponse('Invalid payload', status=400)
	secret = settings.PAYWAY_API_KEY
	message = ''.join(json.dumps(data[key], separators=(',', ':')) if isinstance(data[key], (dict, list)) else str(data[key]) for key in sorted(data))
	expected = base64.b64encode(hmac.new(secret.encode(), message.encode(), hashlib.sha512).digest()).decode()
	provided = request.headers.get('X-PayWay-Hmac-Sha512', '')
	if not secret or not provided or not hmac.compare_digest(expected, provided):
		return HttpResponse('Invalid signature', status=401)
	with transaction.atomic():
		order = Order.objects.select_for_update().filter(transaction_id=data.get('tran_id')).first()
		if not order:
			return HttpResponse('Unknown transaction', status=404)
		if order.payment_status == Order.PaymentStatus.PENDING:
			try:
				paid_total = Decimal(str(data.get('total_amount', 'NaN')))
			except ArithmeticError:
				paid_total = Decimal('NaN')
			if str(data.get('status')) == '0' and paid_total == order.total and data.get('original_currency') == 'USD':
				order.payment_status = Order.PaymentStatus.PAID
				order.status = Order.Status.PROCESSING
			else:
				order.payment_status = Order.PaymentStatus.FAILED
				order.status = Order.Status.CANCELLED
				for item in order.items.select_related('variant'):
					if item.variant_id:
						ProductVariant.objects.filter(pk=item.variant_id).update(stock=models.F('stock') + item.quantity)
					else:
						Product.objects.filter(pk=item.product_id).update(stock=models.F('stock') + item.quantity)
				if order.coupon_code:
					Coupon.objects.filter(code__iexact=order.coupon_code, uses__gt=0).update(uses=models.F('uses') - 1)
			order.save(update_fields=('payment_status', 'status'))
	return HttpResponse('OK')


def order_success(request, public_id):
	query = Order.objects.prefetch_related('items')
	if request.user.is_authenticated:
		order = get_object_or_404(query, public_id=public_id, user=request.user)
	else:
		order = get_object_or_404(query, public_id=public_id, user__isnull=True)
	return render(request, 'shop/success.html', {
		'order': order,
		'order_cancelled': order.status == Order.Status.CANCELLED,
		'payway_pending': order.payment_method == Order.PaymentMethod.PAYWAY and order.payment_status != Order.PaymentStatus.PAID and order.status != Order.Status.CANCELLED,
		'order_confirmed': order.status != Order.Status.CANCELLED and (order.payment_method != Order.PaymentMethod.PAYWAY or order.payment_status == Order.PaymentStatus.PAID),
	})


def register(request):
	form = CustomerRegistrationForm(request.POST or None)
	if request.method == 'POST' and form.is_valid():
		user = form.save()
		login(request, user)
		return redirect('shop:account')
	return render(request, 'shop/auth.html', {'form': form, 'mode': 'register'})


def login_view(request):
	form = AuthenticationForm(request, data=request.POST or None)
	if request.method == 'POST' and form.is_valid():
		login(request, form.get_user())
		next_url = request.POST.get('next') or request.GET.get('next') or reverse('shop:account')
		if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
			next_url = reverse('shop:account')
		return redirect(next_url)
	return render(request, 'shop/auth.html', {'form': form, 'mode': 'login', 'next': request.GET.get('next', '')})


@require_POST
def logout_view(request):
	logout(request)
	return redirect('shop:home')


@login_required
def account(request):
	return render(request, 'shop/account.html', {
		'orders': request.user.shop_orders.prefetch_related('items'),
		'favorites': Product.objects.filter(favorited_by__user=request.user),
		'addresses': request.user.shop_addresses.all(),
	})


@login_required
@require_POST
def favorite_toggle(request, slug):
	product = get_object_or_404(Product, slug=slug, active=True)
	favorite, created = CustomerFavorite.objects.get_or_create(user=request.user, product=product)
	if not created:
		favorite.delete()
	if request.headers.get('x-requested-with') == 'XMLHttpRequest':
		return JsonResponse({'favorite': created})
	return redirect('shop:product_detail', slug=slug)


def policy(request, page):
	pages = {
		'shipping': ('Shipping in Cambodia', 'Phnom Penh delivery is $2; provincial delivery is $4. Orders of $100 or more ship free. We will confirm delivery timing and availability by phone or email before dispatch.'),
		'returns': ('Returns and exchanges', 'Contact SwayStudio within 7 days of delivery to request an exchange or return. Items must be unworn, unwashed, and in original condition. This sample policy must be reviewed against your actual business terms before launch.'),
		'privacy': ('Privacy notice', 'We use customer details to process orders, arrange delivery within Cambodia, and respond to support requests. We do not sell customer data. Account passwords are stored using Django password hashing. Add your legal business identity and data-retention details before launch.'),
	}
	if page not in pages:
		return redirect('shop:home')
	return render(request, 'shop/policy.html', {'title': pages[page][0], 'body': pages[page][1], 'page': page})


def contact(request):
	return render(request, 'shop/contact.html', {'contact_email': getattr(settings, 'STORE_CONTACT_EMAIL', 'hello@swaystudio.example')})