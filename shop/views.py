from decimal import Decimal

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import CheckoutForm
from .models import Order, OrderItem, Product


FREE_SHIPPING_THRESHOLD = Decimal('100.00')
STANDARD_SHIPPING = Decimal('8.00')


def _cart_payload(request):
	cart = request.session.get('cart', {})
	try:
		product_ids = [int(product_id) for product_id in cart]
	except (TypeError, ValueError):
		product_ids = []
		cart = {}

	products = Product.objects.filter(pk__in=product_ids, active=True)
	items = []
	subtotal = Decimal('0.00')
	for product in products:
		try:
			quantity = max(0, min(int(cart.get(str(product.pk), 0)), product.stock))
		except (TypeError, ValueError):
			quantity = 0
		if quantity:
			line_total = product.price * quantity
			subtotal += line_total
			items.append({
				'id': product.pk,
				'slug': product.slug,
				'name': product.name,
				'price': str(product.price),
				'image_url': product.image_url,
				'quantity': quantity,
				'line_total': str(line_total),
				'stock': product.stock,
			})

	shipping = Decimal('0.00') if subtotal >= FREE_SHIPPING_THRESHOLD else (STANDARD_SHIPPING if subtotal else Decimal('0.00'))
	return {
		'items': items,
		'count': sum(item['quantity'] for item in items),
		'subtotal': str(subtotal),
		'shipping': str(shipping),
		'total': str(subtotal + shipping),
		'shipping_label': '—' if not subtotal else ('Free' if not shipping else f'${shipping:.2f}'),
		'free_shipping_threshold': str(FREE_SHIPPING_THRESHOLD),
	}


def home(request):
	products = Product.objects.filter(active=True)
	category = request.GET.get('category', '')
	query = request.GET.get('q', '').strip()
	if category in Product.Category.values:
		products = products.filter(category=category)
	else:
		category = ''
	if query:
		products = products.filter(name__icontains=query) | products.filter(description__icontains=query)
	return render(request, 'shop/home.html', {
		'products': products,
		'categories': Product.Category.choices,
		'selected_category': category,
		'query': query,
		'cart': _cart_payload(request),
	})

def product_detail(request, slug):
	product = get_object_or_404(Product, slug=slug, active=True)
	return render(request, 'shop/product_detail.html', {
		'product': product,
		'cart': _cart_payload(request),
	})


@require_POST
def cart_change(request, slug):
	product = get_object_or_404(Product, slug=slug, active=True)
	cart = request.session.get('cart', {})
	try:
		quantity = int(request.POST.get('quantity', 1))
		current = int(cart.get(str(product.pk), 0))
	except (TypeError, ValueError):
		return JsonResponse({'ok': False, 'error': 'Choose a valid quantity.'}, status=400)

	action = request.POST.get('action', 'add')
	if action == 'add':
		quantity = current + 1
	elif action != 'set':
		return JsonResponse({'ok': False, 'error': 'That cart action is not available.'}, status=400)

	if quantity > product.stock:
		return JsonResponse({'ok': False, 'error': 'There are not enough pieces in stock.'}, status=409)
	if quantity <= 0:
		cart.pop(str(product.pk), None)
	else:
		cart[str(product.pk)] = quantity
	request.session['cart'] = cart
	if request.headers.get('x-requested-with') == 'XMLHttpRequest':
		return JsonResponse({'ok': True, **_cart_payload(request)})
	return redirect('shop:product_detail', slug=slug)


def checkout(request):
	cart = _cart_payload(request)
	form = CheckoutForm(request.POST or None)
	if request.method == 'POST':
		if not cart['items']:
			form.add_error(None, 'Your bag is empty. Add something lovely first.')
		elif form.is_valid():
			try:
				with transaction.atomic():
					product_ids = [item['id'] for item in cart['items']]
					products = {
						product.pk: product
						for product in Product.objects.select_for_update().filter(pk__in=product_ids, active=True)
					}
					if len(products) != len(cart['items']):
						raise ValueError('One of your items is no longer available.')
					for item in cart['items']:
						product = products[item['id']]
						if product.stock < item['quantity']:
							raise ValueError(f'{product.name} no longer has that many in stock.')

					subtotal = sum(
						(products[item['id']].price * item['quantity'] for item in cart['items']),
						Decimal('0.00'),
					)
					shipping = Decimal('0.00') if subtotal >= FREE_SHIPPING_THRESHOLD else STANDARD_SHIPPING
					order = Order.objects.create(
						**form.cleaned_data,
						subtotal=subtotal,
						shipping=shipping,
						total=subtotal + shipping,
					)
					for item in cart['items']:
						product = products[item['id']]
						OrderItem.objects.create(
							order=order,
							product=product,
							product_name=product.name,
							unit_price=product.price,
							quantity=item['quantity'],
						)
						product.stock -= item['quantity']
						product.save(update_fields=('stock',))
			except ValueError as error:
				form.add_error(None, str(error))
			else:
				request.session.pop('cart', None)
				return redirect('shop:order_success', public_id=order.public_id)

	return render(request, 'shop/checkout.html', {'form': form, 'cart': cart})


def order_success(request, public_id):
	order = get_object_or_404(Order.objects.prefetch_related('items'), public_id=public_id)
	return render(request, 'shop/success.html', {'order': order})
