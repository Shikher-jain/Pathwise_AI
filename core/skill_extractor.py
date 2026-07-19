"""Extract skills and keywords from resume text."""
import re

# Master skill list — covers AI/ML, Backend, and general CS
SKILL_KEYWORDS = [
    # Languages
    "python", "sql", "java", "javascript", "typescript", "c++", "go", "rust",
    # AI/ML
    "machine learning", "deep learning", "nlp", "natural language processing",
    "transformers", "bert", "gpt", "llm", "rag", "langchain", "huggingface",
    "pytorch", "tensorflow", "scikit-learn", "xgboost", "computer vision",
    "embeddings", "vector database", "fine-tuning", "lora", "peft",
    "prompt engineering", "generative ai", "genai", "diffusion",
    # Retrieval / Vector
    "faiss", "qdrant", "pinecone", "weaviate", "chroma", "elasticsearch",
    "semantic search", "sentence-transformers",
    # Backend
    "fastapi", "flask", "django", "rest api", "graphql", "grpc",
    "microservices", "async", "celery", "redis", "kafka",
    # Databases
    "postgresql", "mysql", "sqlite", "mongodb", "dynamodb", "firebase",
    # DevOps / Infra
    "docker", "kubernetes", "ci/cd", "github actions", "aws", "gcp", "azure",
    "linux", "nginx", "terraform",
    # Data
    "pandas", "numpy", "etl", "data pipeline", "spark", "airflow",
    "tableau", "power bi", "streamlit",
    # Tools
    "git", "selenium", "scrapy", "beautifulsoup", "playwright",
    # Soft / domain
    "api integration", "web scraping", "data engineering",
    "model deployment", "mlops", "backend engineering",
]

# Common resume stopwords to clean noise
STOPWORDS = {
    "the", "and", "for", "are", "was", "with", "this", "that", "have",
    "from", "they", "will", "been", "has", "had", "but", "not", "what",
    "all", "were", "when", "your", "can", "said", "each", "which",
    "their", "time", "about", "would", "make", "than", "its", "now",
    "into", "only", "over", "also", "use", "two", "how", "our",
}


def extract_skills(text: str) -> list[str]:
    """
    Returns a sorted list of matched skills found in resume text.
    Case-insensitive, multi-word aware.
    """
    text_lower = text.lower()
    found = []
    for skill in SKILL_KEYWORDS:
        pattern = r'\b' + re.escape(skill) + r'\b'
        if re.search(pattern, text_lower):
            found.append(skill)
    return sorted(set(found))


def extract_keywords(text: str, top_n: int = 20) -> list[str]:
    """
    TF-IDF style top keywords from resume text for job search queries.
    Returns top_n most distinctive words.
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    import numpy as np

    # Clean text
    text_clean = re.sub(r'[^a-zA-Z\s]', ' ', text.lower())
    words = [w for w in text_clean.split() if len(w) > 3 and w not in STOPWORDS]
    cleaned = " ".join(words)

    if not cleaned.strip():
        return []

    try:
        vec = TfidfVectorizer(max_features=top_n, ngram_range=(1, 2))
        vec.fit([cleaned])
        return list(vec.get_feature_names_out())
    except Exception:
        # Fallback: simple frequency count
        from collections import Counter
        counts = Counter(words)
        return [w for w, _ in counts.most_common(top_n)]


def build_search_query(skills: list[str], role: str, top_n: int = 5) -> str:
    """Build a compact search query string from role + top skills."""
    top_skills = skills[:top_n]
    parts = [role] + top_skills if role else top_skills
    return " ".join(parts)
