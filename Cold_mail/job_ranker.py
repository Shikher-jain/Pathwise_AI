from __future__ import annotations

from typing import Any


def _rank_with_transformers(resume_text: str, jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from sentence_transformers import SentenceTransformer
    from sklearn.metrics.pairwise import cosine_similarity

    model = SentenceTransformer("all-MiniLM-L6-v2")

    resume_embedding = model.encode([resume_text])[0]
    titles = [str(job.get("title", "")) for job in jobs]
    job_embeddings = model.encode(titles)

    scored: list[dict[str, Any]] = []
    for idx, job in enumerate(jobs):
        job_embedding = job_embeddings[idx]
        score = float(cosine_similarity([resume_embedding], [job_embedding])[0][0])

        row = dict(job)
        row["score"] = score
        scored.append(row)

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


def _rank_with_tfidf(resume_text: str, jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    corpus = [resume_text] + [job.get("title", "") for job in jobs]
    vectorizer = TfidfVectorizer(stop_words="english")
    vectors = vectorizer.fit_transform(corpus)

    resume_vector = vectors[0]
    job_vectors = vectors[1:]
    similarities = cosine_similarity(resume_vector, job_vectors)[0]

    scored: list[dict[str, Any]] = []
    for idx, job in enumerate(jobs):
        row = dict(job)
        row["score"] = float(similarities[idx])
        scored.append(row)

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


def rank_jobs(resume_text: str, jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not jobs:
        return []

    try:
        return _rank_with_transformers(resume_text, jobs)
    except Exception:
        return _rank_with_tfidf(resume_text, jobs)
