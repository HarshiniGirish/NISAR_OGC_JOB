FROM mas.maap-project.org/root/maap-workspaces/base_images/pangeo:v4.1.1

WORKDIR /opt/app

COPY . /opt/app

RUN chmod +x /opt/app/run.sh /opt/app/build.sh && /opt/app/build.sh

ENTRYPOINT ["/opt/app/run.sh"]
