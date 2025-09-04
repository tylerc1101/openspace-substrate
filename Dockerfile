# syntax=docker/dockerfile:1.6
FROM platform-one-ironbank-docker-remote.bits.devops.kratosdefense.com/ironbank/redhat/ubi/ubi8:8.10

# Install required tools
RUN microdnf install -y \
      ca-certificates curl bash coreutils findutils procps iproute \
      openssh-clients gnupg2 git jq yq python39 \
  && microdnf clean all

# Set working directory for onboarder logic
WORKDIR /docker-workspace
COPY docker-workspace/ /docker-workspace/

# Environment defaults (constant across runs)
ENV ANSIBLE_CONFIG=/docker-workspace/ansible/ansible.cfg \
    ANSIBLE_ROLES_PATH=/docker-workspace/ansible/roles:/usr/share/ansible/roles \
    ANSIBLE_COLLECTIONS_PATHS=/docker-workspace/ansible/collections \
    TF_PLUGIN_CACHE_DIR=/docker-workspace/terraform/plugins \
    TF_CLI_CONFIG_FILE=/docker-workspace/terraform/terraformrc \
    PATH="/docker-workspace/tools:${PATH}"

CMD ["/docker-workspace/onboarder.sh", "doctor"]
