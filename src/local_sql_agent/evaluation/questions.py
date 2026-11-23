"""Benchmark questions dataset for local_sql_agent.
Contains 16 questions covering:
- Simple queries (one table, one number)
- Joins across tables
- Grouping & aggregations
- Calculations (percentages, differences, averages)
- Multi-tool / multi-turn questions
- Unanswerable queries (missing schema fields)
"""

from typing import Any, Dict, List

BENCHMARK_QUESTIONS: List[Dict[str, Any]] = [
    {
        "id": "Q01",
        "category": "simple",
        "question": "How many customers are registered in the database?",
        "ground_truth_sql": "SELECT COUNT(*) FROM customers",
        "expected_value": 50,
        "keywords": ["50"],
        "unanswerable": False,
    },
    {
        "id": "Q02",
        "category": "simple",
        "question": "What is the total number of orders placed?",
        "ground_truth_sql": "SELECT COUNT(*) FROM orders",
        "expected_value": 120,
        "keywords": ["120"],
        "unanswerable": False,
    },
    {
        "id": "Q03",
        "category": "simple",
        "question": "How many products belong to the 'Electronics' category?",
        "ground_truth_sql": "SELECT COUNT(*) FROM products WHERE category = 'Electronics'",
        "expected_value": 7,
        "keywords": ["7"],
        "unanswerable": False,
    },
    {
        "id": "Q04",
        "category": "joins",
        "question": "What is the total revenue from completed orders for customer 12?",
        "ground_truth_sql": """
            SELECT ROUND(COALESCE(SUM(oi.quantity * oi.unit_price), 0), 2)
            FROM orders o
            JOIN order_items oi ON o.order_id = oi.order_id
            WHERE o.customer_id = 12 AND o.status = 'completed'
        """,
        "expected_value": 550.89,
        "keywords": ["550.89", "550.9", "551"],
        "unanswerable": False,
    },
    {
        "id": "Q05",
        "category": "joins",
        "question": "How many units of 'Wireless Mouse' were sold across all completed orders?",
        "ground_truth_sql": """
            SELECT COALESCE(SUM(oi.quantity), 0)
            FROM products p
            JOIN order_items oi ON p.product_id = oi.product_id
            JOIN orders o ON o.order_id = oi.order_id
            WHERE p.name = 'Wireless Mouse' AND o.status = 'completed'
        """,
        "expected_value": 13,
        "keywords": ["13"],
        "unanswerable": False,
    },
    {
        "id": "Q06",
        "category": "joins",
        "question": "How many completed orders were placed by customers living in 'Seattle'?",
        "ground_truth_sql": """
            SELECT COUNT(DISTINCT o.order_id)
            FROM orders o
            JOIN customers c ON o.customer_id = c.customer_id
            WHERE c.city = 'Seattle' AND o.status = 'completed'
        """,
        "expected_value": 6,
        "keywords": ["6"],
        "unanswerable": False,
    },
    {
        "id": "Q07",
        "category": "grouping",
        "question": "Which product category generated the highest total revenue from completed orders?",
        "ground_truth_sql": """
            SELECT p.category
            FROM products p
            JOIN order_items oi ON p.product_id = oi.product_id
            JOIN orders o ON o.order_id = oi.order_id
            WHERE o.status = 'completed'
            GROUP BY p.category
            ORDER BY SUM(oi.quantity * oi.unit_price) DESC
            LIMIT 1
        """,
        "expected_value": "Electronics",
        "keywords": ["electronics"],
        "unanswerable": False,
    },
    {
        "id": "Q08",
        "category": "grouping",
        "question": "Which city has the largest number of registered customers?",
        "ground_truth_sql": """
            SELECT city
            FROM customers
            GROUP BY city
            ORDER BY COUNT(*) DESC, city ASC
            LIMIT 1
        """,
        "expected_value": "Denver",
        "keywords": ["denver"],
        "unanswerable": False,
    },
    {
        "id": "Q09",
        "category": "grouping",
        "question": "What is the most frequently purchased product by total quantity in completed orders?",
        "ground_truth_sql": """
            SELECT p.name
            FROM products p
            JOIN order_items oi ON p.product_id = oi.product_id
            JOIN orders o ON o.order_id = oi.order_id
            WHERE o.status = 'completed'
            GROUP BY p.name
            ORDER BY SUM(oi.quantity) DESC
            LIMIT 1
        """,
        "expected_value": "Designing Data-Intensive Apps",
        "keywords": ["designing data-intensive apps", "data-intensive"],
        "unanswerable": False,
    },
    {
        "id": "Q10",
        "category": "calculation",
        "question": "What is the average order revenue across all completed orders in the database?",
        "ground_truth_sql": """
            SELECT ROUND(AVG(order_total), 2)
            FROM (
                SELECT o.order_id, SUM(oi.quantity * oi.unit_price) as order_total
                FROM orders o
                JOIN order_items oi ON o.order_id = oi.order_id
                WHERE o.status = 'completed'
                GROUP BY o.order_id
            )
        """,
        "expected_value": 359.64,
        "keywords": ["359.64", "359.6", "360"],
        "unanswerable": False,
    },
    {
        "id": "Q11",
        "category": "calculation",
        "question": "What is the difference between the most expensive product and the cheapest product?",
        "ground_truth_sql": "SELECT ROUND(MAX(price) - MIN(price), 2) FROM products",
        "expected_value": 237.49,
        "keywords": ["237.49", "237.5"],
        "unanswerable": False,
    },
    {
        "id": "Q12",
        "category": "calculation",
        "question": "What percentage of all orders have 'completed' status?",
        "ground_truth_sql": "SELECT ROUND((COUNT(CASE WHEN status = 'completed' THEN 1 END) * 100.0) / COUNT(*), 2) FROM orders",
        "expected_value": 60.83,
        "keywords": ["60.83", "60.8", "61"],
        "unanswerable": False,
    },
    {
        "id": "Q13",
        "category": "multi_tool",
        "question": "What is the average completed order total, and what percentage is it above the minimum completed order total?",
        "ground_truth_sql": """
            WITH order_totals AS (
                SELECT o.order_id, SUM(oi.quantity * oi.unit_price) as total
                FROM orders o
                JOIN order_items oi ON o.order_id = oi.order_id
                WHERE o.status = 'completed'
                GROUP BY o.order_id
            )
            SELECT 
                ROUND(AVG(total), 2) as avg_total,
                ROUND(MIN(total), 2) as min_total,
                ROUND(((AVG(total) - MIN(total)) / MIN(total)) * 100.0, 2) as pct_above
            FROM order_totals
        """,
        "expected_value": {"avg": 359.64, "min": 12.50, "pct_above": 2777.12},
        "keywords": ["359.64", "2777", "2832"],
        "unanswerable": False,
    },
    {
        "id": "Q14",
        "category": "multi_tool",
        "question": "How much higher is the average price of 'Electronics' products compared to 'Books' products?",
        "ground_truth_sql": """
            SELECT 
                ROUND((SELECT AVG(price) FROM products WHERE category = 'Electronics') -
                      (SELECT AVG(price) FROM products WHERE category = 'Books'), 2) as diff
        """,
        "expected_value": 46.96,
        "keywords": ["46.96", "46.97", "47"],
        "unanswerable": False,
    },
    {
        "id": "Q15",
        "category": "unanswerable",
        "question": "What is the credit score and annual salary of customer 5?",
        "ground_truth_sql": None,
        "expected_value": None,
        "keywords": ["not available", "cannot be answered", "does not contain", "no credit score", "no salary", "not found", "none of the"],
        "unanswerable": True,
    },
    {
        "id": "Q16",
        "category": "unanswerable",
        "question": "What is the warranty period in months for the 27-inch Monitor?",
        "ground_truth_sql": None,
        "expected_value": None,
        "keywords": ["not available", "cannot be answered", "does not contain", "no warranty", "not recorded", "not found", "none of the"],
        "unanswerable": True,
    },
]
