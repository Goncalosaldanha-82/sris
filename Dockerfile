FROM caddy:2.9-alpine
WORKDIR /app
COPY site /app
# Chromium/Edge on Windows can rasterise fixed CSS backgrounds at a reduced
# resolution. The institutional site uses real landscape photographs, so keep
# them attached to the document flow to preserve native sharpness.
RUN sed -i 's/ fixed no-repeat/ no-repeat/g' /app/index.html
COPY Caddyfile /etc/caddy/Caddyfile
EXPOSE 8080
