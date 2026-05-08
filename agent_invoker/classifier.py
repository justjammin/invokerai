from __future__ import annotations

import pickle
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

DEFAULT_PKL = Path.home() / ".invokerai" / "router.pkl"


def predict(task: str, pkl_path: Path = DEFAULT_PKL) -> dict | None:
    if not pkl_path.exists():
        return None

    bundle = pickle.load(open(pkl_path, "rb"))
    phase = bundle.get("phase", 1)

    if phase == 1:
        vec = bundle["vectorizer"].transform([task])
    else:
        from sentence_transformers import SentenceTransformer
        model = _get_model(bundle["model_name"])
        vec = model.encode([task])

    clf = bundle["clf"]
    label: str = clf.predict(vec)[0]
    proba: float = clf.predict_proba(vec).max()

    routing, role = label.split("|", 1)
    return {
        "routing": routing,
        "suggested_role": role if role != "null" else None,
        "confidence": int(proba * 100),
        "source": f"ml-phase{phase}",
    }


def build(
    examples: list[tuple[str, str]],
    output_path: Path = DEFAULT_PKL,
    phase: int = 1,
    model_name: str = "BAAI/bge-large-en-v1.5",
) -> None:
    texts, labels = zip(*examples)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if phase == 1:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.neighbors import KNeighborsClassifier

        vectorizer = TfidfVectorizer(ngram_range=(1, 2), max_features=500)
        X = vectorizer.fit_transform(texts)
        clf = KNeighborsClassifier(n_neighbors=min(5, len(examples)), metric="cosine")
        clf.fit(X, labels)
        payload = {"phase": 1, "vectorizer": vectorizer, "clf": clf}

    else:
        from sentence_transformers import SentenceTransformer
        from sklearn.ensemble import RandomForestClassifier

        model = SentenceTransformer(model_name)
        X = model.encode(list(texts))
        clf = RandomForestClassifier(n_estimators=100, random_state=42)
        clf.fit(X, labels)
        payload = {"phase": 2, "model_name": model_name, "clf": clf}

    pickle.dump(payload, open(output_path, "wb"))
    print(f"Router saved → {output_path}  (phase {phase}, {len(examples)} examples)")


_model_cache: dict[str, object] = {}


def _get_model(name: str):
    if name not in _model_cache:
        from sentence_transformers import SentenceTransformer
        _model_cache[name] = SentenceTransformer(name)
    return _model_cache[name]
