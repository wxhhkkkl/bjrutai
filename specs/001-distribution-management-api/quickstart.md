# Quickstart: 北京儒泰分销管理后端与API

## Prerequisites

- Python 3.11+
- Node.js 18+ (for Vue admin)
- MySQL 8.0 (Tencent Cloud) accessible via network
- Git
- Docker (optional, for containerized deployment)

## Environment Setup

### 1. Clone and navigate

```bash
git clone <repo-url>
cd bjrutai
```

### 2. Backend setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with actual values (see Configuration section below)
```

**.env.example** required variables:

```env
# Database
DATABASE_URL=mysql+aiomysql://user:password@host:3306/dbname?charset=utf8mb4

# WeChat Mini-Program
WECHAT_APP_ID=wxXXXXXXXXXXXXXX
WECHAT_APP_SECRET=your_app_secret

# JWT
JWT_SECRET_KEY=generate-a-random-secret-key
ACCESS_TOKEN_EXPIRE_MINUTES=120
REFRESH_TOKEN_EXPIRE_DAYS=30

# Harbin Rutai API
RUTAI_API_BASE_URL=https://api.rutai.example.com
RUTAI_API_KEY=your_api_key
RUTAI_API_SECRET=your_api_secret

# Tencent Cloud COS
COS_SECRET_ID=your_cos_secret_id
COS_SECRET_KEY=your_cos_secret_key
COS_BUCKET=bjrutai-uploads
COS_REGION=ap-beijing

# Admin
ADMIN_DEFAULT_USERNAME=admin
ADMIN_DEFAULT_PASSWORD=change-me-immediately
```

### 3. Database setup

```bash
# Run migrations
alembic upgrade head

# Seed initial data (L1 root node, default admin account, default roles)
python -m src.seed
```

### 4. Admin frontend setup

```bash
cd ../admin

# Install dependencies
npm install

# Configure API base URL
cp .env.example .env
# Edit VITE_API_BASE_URL in .env

# Start dev server
npm run dev
```

### 5. Start backend

```bash
cd backend

# Development
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Production (with Docker)
docker build -t bjrutai-api .
docker run -d -p 8000:8000 --env-file .env bjrutai-api
```

## Running Tests

### Backend tests (TDD enforced)

```bash
cd backend

# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test type
pytest tests/contract/        # API contract tests
pytest tests/integration/     # Integration tests
pytest tests/unit/            # Unit tests

# Watch mode (for TDD red-green-refactor)
ptw -- --testmon
```

### Admin frontend tests

```bash
cd admin

# Run tests
npm run test

# Watch mode
npm run test:watch
```

## TDD Workflow

Every feature follows this cycle:

```
1. Write a FAILING test (Red)
   ├── Contract test: define expected request/response
   ├── Unit test: define expected service behavior
   └── Integration test: define expected user journey

2. Run tests → confirm they FAIL

3. Write MINIMUM code to pass (Green)
   ├── Schema (Pydantic model)
   ├── Service (business logic)
   └── Router (API endpoint)

4. Refactor (keep green)

5. Commit
```

## API Documentation

Once the backend is running, access auto-generated API docs:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Key API Endpoints

| Module | Base Path | Description |
|--------|-----------|-------------|
| Auth | `/api/v1/auth/` | Login, tokens, session |
| Bootstrap | `/api/v1/app/` | App initialization |
| Profile | `/api/v1/me/` | User profile, avatar |
| Qualifications | `/api/v1/qualifications/` | Qualification CRUD |
| Binding | `/api/v1/binding-requests/` | Customer binding |
| Customers | `/api/v1/customers/` | Customer management |
| Contributions | `/api/v1/contributions/` | Contribution values |
| Team | `/api/v1/team/` | Team contributions |
| Workbench | `/api/v1/workbench/` | Role-based dashboard |
| Reports | `/api/v1/reports/` | Reconciliation reports |
| Articles | `/api/v1/articles/` | Health content |
| Admin | `/api/v1/admin/` | Management console |
| Notifications | `/api/v1/notifications/` | Message center |
| Feedback | `/api/v1/feedbacks/` | User feedback |

## Background Tasks

| Task | Schedule | Description |
|------|----------|-------------|
| `sync-bind-users` | Every 60 seconds | Poll `getBindUser` from Rutai |
| `sync-user-bills` | Triggered per new binding | Query `getUserBill` for new users |
| `monthly-settlement` | 1st of each month, 00:00 | Settle last month's contributions |
| `qualification-expiry-check` | Daily at 09:00 | Check for expiring qualifications |
| `retry-failed-sync` | Every 10 minutes | Retry failed bindUser/bill calls |

## Verification Checklist

After setup, verify everything works:

- [ ] `GET /api/v1/app/bootstrap` returns 200 with valid session
- [ ] `POST /api/v1/auth/admin-login` returns JWT tokens
- [ ] `POST /api/v1/auth/wechat-login` works with test WeChat code
- [ ] `GET /api/v1/qualifications/current` returns qualification status
- [ ] `POST /api/v1/binding-requests` with valid data creates binding
- [ ] `GET /api/v1/contributions/overview` returns contribution summary
- [ ] `GET /docs` shows all API documentation
- [ ] All tests pass: `pytest` exits with 0
- [ ] Admin frontend `npm run dev` loads login page
- [ ] Admin login works with default credentials
