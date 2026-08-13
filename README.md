# Medicare Console (pharmacy-admin)
#
# Architecture (mirrors hotcol / hotcol-user):
# - pharmacy-admin  = Apex console (this project)
# - pharmacy        = Medicare tenant app
# - Shared MySQL    = same DB; tenant key = pharmacy_tin
# - Schema owner    = pharmacy BackEnd (TenantAccount migrations)
# - Apex auth       = Django staff/superuser accounts

## Backend

```powershell
cd BackEnd
.\venv\Scripts\Activate.ps1
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 8000
```

Sign in to the console with that Django superuser (or any `is_staff` user).

API:
- `POST /api/apex/auth/login/`
- `GET/POST /api/tenants/`
- `GET/PATCH /api/tenants/<tin>/`
- `POST /api/tenants/<tin>/<suspend|unsuspend|ban|unban|delete|restore>/`

## Frontend

```powershell
# from pharmacy-admin root
npm install
# .env.local should point at the admin API
# NEXT_PUBLIC_API_URL=http://127.0.0.1:8000/api
npm run dev
```

Open http://localhost:3001/login
