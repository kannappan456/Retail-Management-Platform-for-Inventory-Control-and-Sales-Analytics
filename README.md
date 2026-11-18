# Retail Management Platform for Inventory Control and Sales Analytics

A full-stack retail management platform designed to simplify inventory operations, monitor sales performance, and provide data-driven business insights through analytics, machine learning, and automation.

## Project Overview

The Retail Management Platform is designed to help retailers manage products, vendors, customers, transactions, and inventory through a centralized application.

The platform provides role-based dashboards for Administrators, Vendors, and Customers. It also integrates inventory forecasting, customer segmentation, product recommendations, automated workflows, and business intelligence reporting.

## Key Features

### 1. Marketplace Management
- Vendor registration and approval.
- Product listing and management.
- Customer product browsing.
- Shopping cart and checkout.
- Transaction management.
- Role-based authentication and authorization.

### 2. Inventory Management
- Inventory tracking and stock monitoring.
- Category management.
- Low-stock alerts.
- Demand forecasting.
- Inventory turnover analysis.
- Warehouse assignment and management.

### 3. Customer Intelligence
- Customer analytics and segmentation using K-Means clustering.
- Customer purchase behavior analysis.
- Personalized product recommendations.
- Recommendation system evaluation using Precision@K, Recall@K, and Hit Rate.

### 4. Sales Analytics
- Revenue analysis and monthly trends.
- Vendor performance analysis.
- Product and category performance.
- Marketplace benchmarking.
- Interactive analytics dashboards.

### 5. Machine Learning and Automation
- MLflow experiment tracking.
- Inventory demand forecasting.
- Customer segmentation experiments.
- Product recommendation evaluation.
- Automated workflows using APScheduler.

### 6. Business Intelligence and Reporting
- Interactive BI dashboard.
- Revenue and inventory visualizations.
- Customer analytics summaries.
- PDF report generation.
- Excel report generation.

## Technology Stack

| Component | Technologies |
|---|---|
| Frontend | React 19, Vite |
| Backend | Python, FastAPI |
| Database | MySQL |
| ORM | SQLAlchemy |
| Authentication | JWT, Passlib |
| Data Processing | Pandas, NumPy |
| Machine Learning | Scikit-learn |
| Experiment Tracking | MLflow |
| Workflow Automation | APScheduler |
| Charts and Visualization | Recharts |
| API Communication | Axios |
| Reporting | ReportLab, OpenPyXL |

## Project Structure

```text
Retail-Management-Platform/
│
├── app/
│   ├── customer/
│   ├── inventory/
│   ├── models/
│   ├── recommendation/
│   ├── reports/
│   ├── routes/
│   ├── schemas/
│   ├── database.py
│   ├── main.py
│   ├── mlflow_tracking.py
│   ├── security.py
│   └── workflow_scheduler.py
│
├── dashboard/
│
├── frontend/
│   ├── public/
│   ├── src/
│   ├── package.json
│   └── vite.config.js
│
├── tests/
│   └── Backend test files are maintained
│       in the project root.
│
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## Installation and Setup

### Prerequisites
- Python 3.10 or later.
- Node.js and npm.
- MySQL Server.
- Git.

### 1. Clone the Repository

```bash
git clone https://github.com/kannappan456/Retail-Management-Platform-for-Inventory-Control-and-Sales-Analytics.git
```

Navigate into the project:

```bash
cd Retail-Management-Platform-for-Inventory-Control-and-Sales-Analytics
```

### 2. Backend Setup

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it on Windows:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Configure your local MySQL database connection according to the settings expected by `app/database.py`. Keep database credentials and other secrets in your local environment configuration. Never commit real credentials.

Initialize the database using the project's database setup script:

```bash
python create_tables.py
```

Start the backend:

```bash
python -m uvicorn app.main:app --reload
```

Backend URL: `http://127.0.0.1:8000`

API Documentation: `http://127.0.0.1:8000/docs`

### 3. Frontend Setup

Open a separate terminal:

```bash
cd frontend
```

Install dependencies:

```bash
npm install
```

Start the development server:

```bash
npm run dev
```

Frontend URL: `http://localhost:5173`

## Application Roles

**Administrator**
- Manage marketplace operations.
- Monitor vendors, products, and transactions.
- Access marketplace-wide analytics.
- Monitor inventory, MLflow experiments, and automated workflows.
- Generate business intelligence reports.

**Vendor**
- Manage products and inventory.
- Monitor vendor-specific sales analytics.
- View customer orders containing their products.

**Customer**
- Browse available products.
- Manage shopping cart and checkout.
- View order history.
- Manage profile and wishlist.
- Access product recommendations.

## Machine Learning Components

- **Demand Forecasting:** Analyzes historical inventory and transaction data to estimate future demand.
- **Customer Segmentation:** Uses K-Means clustering to group customers based on purchasing behavior.
- **Product Recommendations:** Uses item-item collaborative filtering with cosine similarity.
- **Model Tracking:** MLflow records experiment runs, parameters, metrics, and artifacts.

## Testing

The project includes automated backend tests covering authentication, inventory operations, customer analytics, recommendations, revenue analytics, reporting, and workflow functionality.

Frontend quality checks:

```bash
npm run lint
npm run build
```

## Project Objective

The primary objective is to develop an integrated retail management solution that combines inventory control, sales analytics, machine learning, and business intelligence to support efficient retail operations and informed decision-making.

## Repository

GitHub: https://github.com/kannappan456/Retail-Management-Platform-for-Inventory-Control-and-Sales-Analytics

---

**Project Title:** Retail Management Platform for Inventory Control and Sales Analytics