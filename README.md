# StockFlow — Feature & Project Documentation

_Last updated: 2026-04-17_

## 1) What this app is
StockFlow is a Django-based marketplace workflow app for two account types:
- **Buyers**: browse items, manage cart, checkout, track orders, manage profile/addresses/wallet.
- **Sellers**: create and manage inventory, receive order-item approval requests, approve/reject items, receive wallet credits.

The app uses session-based auth, server-rendered HTML templates, and role-based route access.

---

## 2) App outline and how it works

### Core architecture
- **Framework**: Django
- **Main app**: `core`
- **Routing**:
  - `config/urls.py` includes `core.urls`
  - `core/urls.py` maps all UI + API endpoints
- **Data layer**: models for buyer/seller, products, inventory, carts, orders, notifications, wallets, transactions.
- **Views**: mostly in `core/views.py`; chatbot endpoint in `core/chatbot_view.py`; Google sign-in in `core/google_oauth.py`.

### Authentication/session model
- Google sign-in only: `/auth/signin` (page with Buyer/Seller choice) → `/auth/google` → Google → `/auth/google/callback`
- `/auth/signup` redirects to `/auth/signin`; sign out via `/auth/signout` (or JSON `POST /signout`)
- Session keys drive identity:
  - `user_id`
  - `user_type` (`buyer` or `seller`)
  - `user_name`

### Roles
- **Buyer-only areas**: cart, checkout, buyer order history, buyer-centric profile actions.
- **Seller-only areas**: inventory creation/editing, order item approval/rejection.
- Shared pages: home, items list, profile, notifications, wallet, address add.

---

## 3) Detailed feature inventory

## A. Authentication and account lifecycle
- "Continue with Google" sign-in (OAuth 2.0 authorization code flow with PKCE, no extra libraries).
- The user picks Buyer or Seller first; the same Google account can hold one buyer and one seller account.
- First sign-in creates the account (name from Google, phone added later on the profile page) and its wallet.
- Session key is rotated on sign-in; flash-message feedback on errors.
- Session invalidation on signout.
- Account deletion (`delete_account`) with session flush.

## B. Google sign-in details
- Only Google-verified emails are accepted; the ID token's issuer, audience and expiry are checked.
- `state` (CSRF) and PKCE `code_verifier` live in the session and are single-use.
- No passwords or emails are sent by the app, so there is no OTP, forgot-password or SMTP setup.
- Configure `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` (Google Cloud Console → OAuth client, type "Web application") and register `https://<host>/auth/google/callback/` as a redirect URI for every host you use.
- Full setup, design decisions and troubleshooting: [`google-oauth.md`](google-oauth.md).

## C. Marketplace item discovery
- `/items` page for in-stock products only.
- `/items/sold-out` for stock-depleted products.
- Search by:
  - product name
  - description
  - SKU
  - category name
- Item health/status tags:
  - In stock
  - Low stock
  - Sold out
- Product rows include seller details and warehouse coverage stats.

## D. Product detail and cart entry
- `/items/<id>/` shows:
  - seller
  - stock totals
  - warehouse location count
  - stock status
- Buyer add-to-cart with quantity checks against available stock.
- Prevent over-adding beyond inventory.

## E. Seller inventory management
- `/inventory` supports seller-only create/update.
- Product fields: name, description, image URL/file upload, SKU, price, category.
- Inventory fields: quantity, warehouse location (Address FK).
- Category options:
  - select existing category
  - create category inline
- SKU uniqueness checks for both create and edit paths.

## F. Address management
- Buyers and sellers can add addresses.
- Default address toggle (`set_default_address`) for both account types.
- Buyer address deletion from profile.
- Seller addresses reused as warehouse locations in inventory flow.

## G. Cart and checkout
- Cart view with:
  - per-line totals
  - subtotal
  - stock sufficiency indicators
  - address selection
- Cart update/remove endpoints.
- Checkout validates:
  - signed-in buyer
  - valid buyer address
  - non-empty cart
  - stock availability across inventories
  - wallet balance

## H. Order workflow + escrow logic
- Checkout creates order in **Pending** state.
- Buyer wallet is debited immediately and tracked as transaction.
- Per-item seller approval model (`OrderItem.status`: Pending/Approved/Rejected).
- If **all sellers approve**:
  - order marked Confirmed
  - inventory deducted
  - seller wallets credited by their item totals
- If **any seller rejects**:
  - order marked Rejected
  - all pending items auto-rejected
  - buyer wallet refunded

## I. Notifications system
- Notifications for both buyer and seller personas.
- Types include:
  - order placed / approval requests
  - item approved/rejected
  - order confirmed/rejected
  - wallet debited/credited/refunded
- Mark single notification read.
- Mark all notifications read.
- Navbar unread badge support via helper.

## J. Wallet and transactions
- One wallet per buyer/seller (`OneToOne`).
- Auto-create wallet when needed.
- Wallet page shows balance + transaction history + credit/debit stats.
- Add-funds endpoint (fixed ₹10,000 credit action).
- Transaction audit includes debit/credit/refund/add-funds with post-balance.

## K. Profile and history
- Profile shows role-specific summary:
  - buyers: total spent + their orders/addresses
  - sellers: total earned from approved items + seller-relevant orders
- Buyer can update name and phone (email comes from Google).
- Buyers can remove non-pending orders.

## L. Chatbot customer service
- `/chatbot/` POST endpoint.
- Uses Gemini API (`gemini-2.5-flash`) with server-side system prompt.
- Builds role-aware context from live DB snapshot:
  - buyer: recent orders, cart, unread notifications
  - seller: product stock + pending approvals + unread notifications
  - catalog snippet for product grounding
- Chat history support with bounded context window.

## M. Hosting support documentation
- `cloudflare-tunnel.md` added to explain local app exposure via Cloudflare Tunnel.

## N. Vercel deployment
- Deployed as a single Vercel Function (zero-config Django detection via `manage.py` / `WSGI_APPLICATION`).
- **Database**: Neon Postgres (Vercel Marketplace). `DATABASE_URL` switches settings to Postgres; without it, local dev keeps SQLite.
- **Migrations** run on every Vercel build (`[tool.vercel.scripts] build` in `pyproject.toml`); `collectstatic` runs automatically (`STATIC_ROOT`).
- **Uploads**: product images go to a public Vercel Blob store via `core/storage.py` when `BLOB_READ_WRITE_TOKEN` is set.
- **Env vars** (Preview + Production): `DJANGO_SECRET_KEY`, `DEBUG=False`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GEMINI_API_KEY`; Neon/Blob vars are injected by the integrations.
- Deploy: connected to GitHub — pushes to any branch create a protected preview (with its own Neon database branch); merging into `main` deploys production.

---

## 4) Data model outline
Main entities and responsibilities:
- `Buyer`, `Seller`: role-specific user records
- `Address`: buyer/seller addresses + default flag
- `Category`, `Product`, `Inventory`: catalog and stock
- `Cart`, `CartProduct`: buyer cart and selected quantities
- `Order`, `OrderItem`: multi-seller order with item-level approval statuses
- `Notification`: role-targeted event feed
- `Wallet`, `Transaction`: balance and accounting trail

---

## 5) End-to-end behavior (high-level)

### Buyer journey
1. Continue with Google as a buyer (account created on first sign-in).
2. Browse/search items.
3. Add item(s) to cart.
4. Select address and checkout.
5. Wallet debited; order enters Pending.
6. Receive notifications as sellers approve/reject.
7. If confirmed: order proceeds and seller payouts occur.
8. If rejected: full refund notification + transaction record.

### Seller journey
1. Continue with Google as a seller.
2. Add/update products and inventory (with categories and warehouse addresses).
3. Receive approval-request notifications for order items.
4. Approve/reject each pending item.
5. On full order approval, wallet credit posted automatically.

---

### Comment-derived collaboration patterns
From issue comments:
- Work was frequently assigned/claimed directly in issue threads.
- Checkpoint issue (#33) was used as QA sweep/triage and encouraged creation of sub-issues for discovered bugs.
- UI/UX refinements were often iterated after review comments (navigation consistency, styling, text fixes).
- Notification-first dependency for wallet behavior was explicitly coordinated in comments.



