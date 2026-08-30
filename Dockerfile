FROM python:3.12-alpine
WORKDIR /app
COPY contact_server.py /app/contact_server.py
COPY site /app/site
RUN addgroup -S sris && adduser -S -G sris sris && chown -R sris:sris /app
USER sris
EXPOSE 8080
CMD ["python", "/app/contact_server.py"]
