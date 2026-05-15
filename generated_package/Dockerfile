FROM mas.maap-project.org/root/maap-workspaces/custom_images/maap_base:v5.0.0

WORKDIR /opt/app

COPY . /opt/app

RUN chmod +x /opt/app/run.sh /opt/app/build.sh && /opt/app/build.sh

ENTRYPOINT ["/opt/app/run.sh"]
