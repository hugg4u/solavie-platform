FROM quay.io/keycloak/keycloak:26.1.2 as builder

# Enable health and metrics support
ENV KC_HEALTH_ENABLED=true
ENV KC_METRICS_ENABLED=true

# Configure a database vendor
ENV KC_DB=postgres

# Enable organization feature
ENV KC_FEATURES=organization

WORKDIR /opt/keycloak
# Build the optimized Keycloak server
RUN /opt/keycloak/bin/kc.sh build

FROM quay.io/keycloak/keycloak:26.1.2
COPY --from=builder /opt/keycloak/ /opt/keycloak/

# Enable organization feature in runtime
ENV KC_FEATURES=organization

# Entrypoint will start the server
ENTRYPOINT ["/opt/keycloak/bin/kc.sh"]
