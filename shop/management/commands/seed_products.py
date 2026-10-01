from django.core.management.base import BaseCommand

from shop.models import Product, ProductVariant


PRODUCTS = [
    ('White & Gray Graphic Tee', 'boys-white-gray-graphic-tee', 'tops', '10.99', 'boys-1.jpg', True),
    ('High Street Gray Tee', 'boys-high-street-gray-tee', 'tops', '12.99', 'boys-2.jpg', True),
    ('Classic Polo Shirt', 'boys-classic-polo-shirt', 'tops', '13.99', 'boys-3.jpg', False),
    ('Cleanfit White Flared Trousers', 'boys-cleanfit-white-flared-trousers', 'bottoms', '14.99', 'boys-4.jpg', True),
    ('Gray Crewneck Sweatshirt', 'boys-gray-crewneck-sweatshirt', 'outerwear', '16.99', 'boys-5.jpg', True),
    ('Casual Straight-Leg Trousers', 'boys-casual-straight-leg-trousers', 'bottoms', '14.99', 'boys-6.jpg', False),
    ('Embroidered Gray Sweatpants', 'boys-embroidered-gray-sweatpants', 'bottoms', '16.99', 'boys-7.jpg', False),
    ('Retro Patchwork Sweatpants', 'boys-retro-patchwork-sweatpants', 'bottoms', '19.99', 'boys-8.jpg', True),
    ('White Embroidered Wide-Leg Jeans', 'girls-white-embroidered-wide-leg-jeans', 'bottoms', '14.99', 'girls-1.jpg', True),
    ('Light Blue Flare Jeans', 'girls-light-blue-flare-jeans', 'bottoms', '14.99', 'girls-2.jpg', False),
    ('Pink Straight-Leg Jeans', 'girls-pink-straight-leg-jeans', 'bottoms', '12.99', 'girls-3.jpg', False),
    ('Distressed White Jeans', 'girls-distressed-white-jeans', 'bottoms', '16.99', 'girls-4.jpg', False),
    ('Dark Blue Wide-Leg Jeans', 'girls-dark-blue-wide-leg-jeans', 'bottoms', '18.99', 'girls-5.jpg', True),
    ('V-Neck Short-Sleeve Tee', 'girls-v-neck-short-sleeve-tee', 'tops', '9.99', 'girls-6.jpg', True),
    ('Korean V-Neck Thermal Top', 'girls-korean-v-neck-thermal-top', 'tops', '11.99', 'girls-7.jpg', False),
    ('Half-Sleeve Graphic Top', 'girls-half-sleeve-graphic-top', 'tops', '10.99', 'girls-8.jpg', False),
    ('Sweet Polka-Dot Top', 'girls-sweet-polka-dot-top', 'tops', '11.99', 'girls-9.jpg', False),
    ('Y2K Star Graphic Tee', 'girls-y2k-star-graphic-tee', 'tops', '11.99', 'girls-10.jpg', True),
    ('Tie-Dye Graphic Top', 'girls-tie-dye-graphic-top', 'tops', '10.99', 'girls-11.jpg', False),
    ('Star Print Lounge Pants', 'girls-star-print-lounge-pants', 'bottoms', '12.99', 'girls-12.jpg', False),
    ('Ribbed V-Neck Long-Sleeve Top', 'girls-ribbed-v-neck-long-sleeve-top', 'tops', '8.99', 'girls-13.jpg', False),
    ('Embroidered Snowflake Hoodie', 'girls-embroidered-snowflake-hoodie', 'outerwear', '19.99', 'girls-14.jpg', True),
    ('High Street Snowflake Hoodie', 'girls-high-street-snowflake-hoodie', 'outerwear', '18.99', 'girls-15.jpg', False),
    ('Floral Embroidered Hoodie', 'girls-floral-embroidered-hoodie', 'outerwear', '18.99', 'girls-16.jpg', False),
    ('Graphic Print Hoodie', 'girls-graphic-print-hoodie', 'outerwear', '17.99', 'girls-17.jpg', False),
    ('Pink Little Bear Lounge Pants', 'girls-pink-little-bear-lounge-pants', 'bottoms', '14.99', 'girls-18.jpg', False),
]

LEGACY_SAMPLE_SLUGS = (
    'sunday-feeling-shirt', 'rosie-slip-dress', 'cloud-nine-cardigan', 'easy-does-it-trouser',
    'daydream-blouse', 'petal-knit-tank', 'weekend-carryall', 'afterglow-midi-dress',
)

DESCRIPTIONS = {
    'tops': 'An easy everyday top from our new imported collection.',
    'bottoms': 'A versatile wardrobe staple, selected for comfortable everyday wear.',
    'outerwear': 'A relaxed extra layer with thoughtful graphic and embroidered details.',
    'dresses': 'An easy-to-wear piece from our imported collection.',
    'accessories': 'A useful finishing touch for everyday outfits.',
}


class Command(BaseCommand):
    help = 'Load the imported boys and girls fashion collections.'

    def handle(self, *args, **options):
        for name, slug, category, price, image_name, featured in PRODUCTS:
            image_alt = f'{name}, shown in a supplier product photo'
            saved_product, _ = Product.objects.update_or_create(
                slug=slug,
                defaults={
                    'name': name,
                    'category': category,
                    'description': DESCRIPTIONS[category],
                    'price': price,
                    'image_url': f'/static/shop/products/{image_name}',
                    'image_alt': image_alt,
                    'badge': 'New arrival' if featured else '',
                    'featured': featured,
                    'active': True,
                },
            )
            sizes = ('One size',) if saved_product.category == Product.Category.ACCESSORIES else ('XS', 'S', 'M', 'L', 'XL')
            colors = {
                'tops': [('Rose', '#F29FA0'), ('Ivory', '#F1EAE2')],
                'dresses': [('Rose', '#F29FA0'), ('Ink', '#302C2C')],
                'bottoms': [('Ink', '#302C2C'), ('Oat', '#C8B8A5')],
                'outerwear': [('Oat', '#C8B8A5'), ('Rose', '#F29FA0')],
                'accessories': [('Rose', '#F29FA0'), ('Ivory', '#F1EAE2')],
            }[saved_product.category]
            for size in sizes:
                for color, color_hex in colors:
                    ProductVariant.objects.get_or_create(
                        product=saved_product,
                        size=size,
                        color_name=color,
                        defaults={
                            'sku': f'SS-{saved_product.pk:03d}-{size.upper().replace(" ", "")}-{color.upper()[:3]}',
                            'color_hex': color_hex,
                            'stock': 12 if size == 'One size' else 4,
                        },
                    )
        Product.objects.filter(slug__in=LEGACY_SAMPLE_SLUGS).update(active=False)
        self.stdout.write(self.style.SUCCESS(f'Loaded {len(PRODUCTS)} SwayStudio products.'))