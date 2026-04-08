FROM nginx:alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

COPY v2_enhanced.html v2_enhanced.js /usr/share/nginx/html/

EXPOSE 80

ENTRYPOINT ["/docker-entrypoint.sh"]
