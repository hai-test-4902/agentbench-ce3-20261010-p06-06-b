FROM python@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 AS build
WORKDIR /build
ENV PIP_CACHE_DIR=/build/.cache/pip
COPY pyproject.toml README.md LICENSE requirements-check.txt ./
COPY src ./src
RUN python -m venv .venv && .venv/bin/pip wheel --constraint requirements-check.txt --wheel-dir wheels .

FROM python@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
WORKDIR /app
COPY --from=build /build/wheels /app/wheels
RUN python -m venv /app/.venv && /app/.venv/bin/pip install --no-cache-dir --no-index --find-links=/app/wheels quakewatch && rm -rf /app/wheels && chown -R 10001:10001 /app
USER 10001:10001
ENV PATH=/app/.venv/bin:$PATH
ENTRYPOINT ["quakewatch"]
CMD ["list", "--window", "day"]
