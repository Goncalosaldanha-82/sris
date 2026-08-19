FROM caddy:2-alpine
WORKDIR /app
COPY Caddyfile /etc/caddy/Caddyfile
COPY site /app
EXPOSE 8080
CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
