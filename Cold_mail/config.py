from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
UPLOADS_DIR = BASE_DIR / "uploads" / "resumes"
GENERATED_DIR = BASE_DIR / "generated"
DATABASE_DIR = BASE_DIR / "database"
TEMPLATES_DIR = BASE_DIR / "templates"

DEFAULT_RESUME_NAME = "resume.pdf"
DEFAULT_HR_CSV_NAME = "hr.csv"
DEFAULT_EMAIL_LOG_NAME = "email_log.csv"

DAILY_EMAIL_LIMIT = 200
HOURLY_EMAIL_LIMIT = 50
SEND_DELAY_SECONDS = 5
SEARCH_MAX_WORKERS = 6

DEFAULT_SKILLS = [
    # Programming Languages
    "python", "java", "c++", "c#", "javascript", "typescript", "go", "ruby", "php", "swift", "kotlin", "scala", "r", "matlab", "bash", "shell scripting",
    # Frameworks & Libraries
    "pytorch", "tensorflow", "keras", "scikit-learn", "pandas", "numpy", "matplotlib", "seaborn", "flask", "django", "fastapi", "spring", "react", "angular", "vue.js", "express.js", "node.js", "bootstrap", "tailwindcss",
    # Data & ML
    "machine learning", "deep learning", "nlp", "computer vision", "data science", "data analysis", "data engineering", "big data", "sql", "nosql", "mongodb", "postgresql", "mysql", "oracle", "hadoop", "spark", "etl", "feature engineering", "model deployment", "mlops",
    # DevOps & Cloud
    "docker", "kubernetes", "ci/cd", "jenkins", "github actions", "aws", "azure", "gcp", "cloud computing", "terraform", "ansible", "linux", "unix", "nginx", "apache", "devops",
    # APIs & Backend
    "api", "rest api", "graphql", "backend", "microservices", "serverless", "web services", "authentication", "authorization",
    # Frontend
    "html", "css", "javascript", "typescript", "react", "angular", "vue.js", "redux", "next.js", "webpack", "sass", "less",
    # Tools
    "git", "jira", "confluence", "slack", "notion", "excel", "powerpoint", "tableau", "power bi", "jira", "postman", "figma", "adobe xd", "photoshop",
    # Soft Skills
    "communication", "teamwork", "leadership", "problem solving", "critical thinking", "adaptability", "time management", "project management", "agile", "scrum", "kanban",
    # Other
    "testing", "unit testing", "integration testing", "tdd", "bdd", "automation", "scripting", "research", "presentation", "mentoring", "training", "customer support", "salesforce", "crm",
]
