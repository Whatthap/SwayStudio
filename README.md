# SwayStudio

A Cambodia-focused clothing storefront built with Django, HTML, CSS, and vanilla JavaScript. It includes size/color SKU inventory, a size guide, USD prices with configurable KHR estimates, Cambodia province delivery, customer accounts with saved addresses and favorites, reviews, related-product browsing, discount codes, order operations, and SQLite by default.

## Run locally

Python 3.10 or newer is recommended; it uses Django 5.2 LTS. Python 3.9 uses the final Django 4.2 patch only for local compatibility and is no longer supported upstream.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_products
python manage.py runserver
```

Open `http://127.0.0.1:8000/`. Create an administrator with `python manage.py createsuperuser`, then visit `/admin/` to manage products/SKUs, stock, orders, coupon codes, and moderated reviews. The seed command creates sample products and size/color stock once; rerunning it does not reset existing SKU quantities.

## Cambodia settings

Prices are stored and charged in USD. KHR labels are estimates using `CAMBODIA_KHR_PER_USD` (default `4100`), which should be reviewed and updated for the store's chosen rate. Delivery defaults are `$2` in Phnom Penh and `$4` in other provinces, free from `$100`; configure them with `CAMBODIA_SHIPPING_PHNOM_PENH` and `CAMBODIA_SHIPPING_PROVINCES`. Cambodian phone numbers are validated with `+855` or local `0` prefixes. The address form includes Cambodia's provinces and cities.

## Payments

Cash on delivery is enabled. ABA PayWay is wired for the documented signed purchase request and HMAC-verified callback, but the option is hidden until the merchant ID and API key are configured. Start with the [ABA PayWay sandbox](https://sandbox.payway.com.kh/register-sandbox/) and official [eCommerce checkout guide](https://developer.payway.com.kh/online-payment-3158159f0.md). Set these in the server environment (never commit the API key):

```sh
export PAYWAY_MERCHANT_ID='your-sandbox-merchant-id'
export PAYWAY_API_KEY='your-sandbox-api-key'
export PAYWAY_BASE_URL='https://checkout-sandbox.payway.com.kh'
```

The callback URL must be reachable over HTTPS and allowlisted in the ABA merchant profile. Localhost cannot receive ABA callbacks unless exposed through an approved tunnel. Swap to the production base URL and production credentials only after sandbox verification. A failed signed callback cancels the order and releases reserved SKU stock; the success page remains pending until a matching signed amount/currency callback arrives.

## Store launch checklist

Set `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=0`, and `DJANGO_ALLOWED_HOSTS`; configure HTTPS and secure cookie settings at the deployment layer. Set `STORE_CONTACT_EMAIL` to the real store inbox. Review the sample shipping, returns, and privacy page copy against the actual business terms. Replace the external sample photos/fonts with licensed assets and replace sample sizes, colors, and inventory in Admin. Checkout currently has no tax calculation or payment refunds workflow; configure these for the actual business before launch.

Run the regression suite with `python manage.py test shop`.

## Temporary public preview on Render

The `render.yaml` Blueprint defines a free web service and free PostgreSQL database for previewing the storefront. Push the project to GitHub, then in Render choose **New > Blueprint**, connect the `Whatthap/SwayStudio` repository, and apply the Blueprint. Enter the real `STORE_CONTACT_EMAIL` in Render when prompted. Render will provide the public `.onrender.com` URL after the first deploy.

### Do not take real orders on the free tier

The free tier deletes your data. The exact limits, as documented by Render:

- **The database is destroyed 30 days after creation.** A free PostgreSQL instance expires, then has a 14-day grace period to upgrade, and is then deleted *along with all of its data*. Every order, account, address, and review in it is lost with no backup. Free PostgreSQL also has no backup support at all and is capped at 1 GB.
- **The web service sleeps after 15 minutes** without inbound traffic and takes roughly a minute to wake, during which visitors get a loading page instead of your site.
- **The filesystem is ephemeral.** Anything written to local disk is lost on every redeploy, restart, or spin-down. This is why the Blueprint uses `DATABASE_URL` for state instead of the local `db.sqlite3`. Free instances cannot attach a persistent disk.
- **Free instances may be restarted at any time**, and free web services get no SSH shell.

Only one free PostgreSQL database is allowed per workspace. Render does not grant free PostgreSQL to every new account, so the Blueprint may ask for a payment method at that step.

Because of the above, treat this strictly as a clickable demo: sample seeded inventory, cash on delivery, no real payments. Move to a paid plan with a persistent database before accepting real orders. The cheapest always-on option is a Fly.io machine with a persistent volume running the existing SQLite; the simplest managed option is a Render Starter web service plus a paid PostgreSQL instance.

The preview uses sample seeded inventory and cash on delivery; configure the real business contact, policies, shipping, stock, and payment details before launch.
