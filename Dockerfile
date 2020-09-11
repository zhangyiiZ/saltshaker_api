FROM saltshaker_endenv:1
MAINTAINER  yongpeng1 for sina as <yueyongyue@sina.cn>
ENV TZ "Asia/Shanghai"
ENV S "saltshaker.conf"

RUN set -xe \
    && echo "https://mirror.tuna.tsinghua.edu.cn/alpine/v3.4/main" > /etc/apk/repositories \
    && rm -rf /data0/saltshaker_api \
    && git clone --depth 1 https://github.com/zhangyiiZ/saltshaker_api.git -b master /data0/saltshaker_api \
    && echo "${TZ}" > /etc/timezone \
    && ln -sf /usr/share/zoneinfo/${TZ} /etc/localtimeDockerfile

CMD cd /data0/saltshaker_api/ && \
sed -i "s/\(MYSQL_HOST = \).*/\1${MYSQL_HOST}/g" ${S} &  & \
sed -i "s/\(MYSQL_PORT = \).*/\1${MYSQL_PORT}/g" ${S} && \
sed -i "s/\(MYSQL_USER = \).*/\1${MYSQL_USER}/g" ${S} && \
sed -i "s/\(MYSQL_PASSWORD = \).*/\1${MYSQL_PASSWORD}/g" ${S} && \
sed -i "s/\(MYSQL_DB = \).*/\1${MYSQL_DB}/g" ${S} && \
sed -i "s/\(MYSQL_CHARSET = \).*/\1${MYSQL_CHARSET}/g" ${S} && \
sed -i "s/\(REDIS_HOST = \).*/\1${REDIS_HOST}/g" ${S} && \
sed -i "s/\(REDIS_PORT = \).*/\1${REDIS_PORT}/g" ${S} && \
sed -i "s/\(REDIS_PASSWORD = \).*/\1${REDIS_PASSWORD}/g" ${S} && \
sed -i "s/\(BROKER_HOST = \).*/\1${BROKER_HOST}/g" ${S} && \
sed -i "s/\(BROKER_PORT = \).*/\1${BROKER_PORT}/g" ${S} && \
sed -i "s/\(BROKER_USER = \).*/\1${BROKER_USER}/g" ${S} && \
sed -i "s/\(BROKER_PASSWORD = \).*/\1${BROKER_PASSWORD}/g" ${S} && \
#sed -i "s/\(BROKER_VHOST = \).*/\1${BROKER_VHOST}/g" ${S} && \
sed -i "s/\(FROM_ADDR = \).*/\1${FROM_ADDR}/g" ${S} && \
sed -i "s/\(MAIL_PASSWORD = \).*/\1${MAIL_PASSWORD}/g" ${S} && \
sed -i "s/\(SMTP_SERVER = \).*/\1${SMTP_SERVER}/g" ${S} && \
sed -i "s/\(SMTP_PORT = \).*/\1${SMTP_PORT}/g" ${S} && \
supervisord -c supervisord.conf
EXPOSE 9000
