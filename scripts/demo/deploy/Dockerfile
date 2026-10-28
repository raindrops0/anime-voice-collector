# The online demo, for a small container host such as Render's free web service (512 MB, a tenth
# of a CPU). make_deploy.py copies this file, the packed demo workspace and a built avoc wheel into one
# folder; see docs/CONTRIBUTING.md#online-demo.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
# Only what serving needs. No torch: without it the guesses are trained with SciPy (avoc.model),
# and the models that add episodes are left out, since the demo cannot add episodes.
COPY wheels/ /wheels/
RUN pip install --no-cache-dir --no-deps /wheels/*.whl \
    && pip install --no-cache-dir "fastapi>=0.143" "uvicorn>=0.30" "numpy>=2.5" "scipy>=1.18" \
    "scikit-learn>=1.6" "soundfile>=0.14" "pysubs2>=1.9" "charset-normalizer>=3.4" \
    "pyloudnorm>=0.2" "typer>=0.27" "audioread>=3.1" "huggingface-hub>=1.0"

RUN useradd -m -u 1000 user
USER user
# One math thread: the container sees every core of the host but may use a tenth of one, and
# a thread per core made each label take seconds instead of under one.
ENV HOME=/home/user PORT=8000 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
COPY --chown=user template/ /home/user/template/
EXPOSE 8000
# The port comes from PORT, which hosts such as Render set themselves.
CMD ["python", "-m", "avoc.app.demo", "serve", "/home/user/template", "--host", "0.0.0.0"]
