#!/bin/bash

ROOT_DIR="$(dirname "$(readlink -f "${BASH_SOURCE}")")"
BASE_DIR="/var/lib/libvirt/config/vm_config/opnsense"
CONFIG_STATE_FILE="${BASE_DIR}/config.env"
CONFIG_XML="${BASE_DIR}/config.xml"

. "${ROOT_DIR}/_helpers.sh"
. "${CONFIG_STATE_FILE}"

# Write Configuration File containing variables used to create config.xml.
# Variables are populated via prompts.
write_config_state_file() {
	echo "Writing Configuration..."
  	cat > ${CONFIG_STATE_FILE} <<-EOF
	OSDC1_MAC="${osdc1_mac}"
	WAN_IP="${wan_ip}"
	WAN_GATEWAY="${wan_gateway}"
	WAN_SUBNET="${wan_subnet}"
	NTP_TIMESERVERS="${ntp_timeservers}"
	NTP_PREFER="${ntp_prefer}"
	OPNSENSE_HOSTNAME="${opnsense_hostname}"
	OPNSENSE_DOMAIN="${opnsense_domain}"
	INTERFACE_WAN="${interface_wan}"
	INTERFACE_LAN="${interface_lan}"
	INTERFACE_OPT1="${interface_opt1}"
	EOF

	if [[ $? -ne 0 ]]; then
		echo '[ERROR] Configuration Write failed. Quitting.'
		exit 1
	fi
}

create_config_xml() {
	# Reloading Config.
	. "${CONFIG_STATE_FILE}"
	echo "Creating OPNSense Configuration..."
	sed -e "s|__OSDC1_MAC__|${OSDC1_MAC}|g" \
		-e "s|__WAN_IP__|${WAN_IP}|g" \
		-e "s|__WAN_GATEWAY__|${WAN_GATEWAY}|g" \
		-e "s|__WAN_SUBNET__|${WAN_SUBNET}|g" \
		-e "s|__NTP_TIMESERVERS__|${NTP_TIMESERVERS}|g" \
		-e "s|__NTP_PREFER__|${NTP_PREFER}|g" \
		-e "s|__OPNSENSE_HOSTNAME__|${OPNSENSE_HOSTNAME}|g" \
		-e "s|__OPNSENSE_DOMAIN__|${OPNSENSE_DOMAIN}|g" \
		-e "s|__INTERFACE_WAN__|${INTERFACE_WAN}|g" \
		-e "s|__INTERFACE_LAN__|${INTERFACE_LAN}|g" \
		-e "s|__INTERFACE_OPT1__|${INTERFACE_OPT1}|g" \
		"${BASE_DIR}/config_template.xml" > "${BASE_DIR}/config.xml"
	if [[ $? -ne 0 ]]; then
		echo "Variable replacement failed. Quiting."
		exit 1
	else
		echo "Configuration saved."
	fi
}

prompt "Customer Network OPNSense WAN IP" wan_ip "${WAN_IP}" "non-empty"
prompt "Customer Network OPNSense WAN Gateway IP" wan_gateway "${WAN_GATEWAY}" "non-empty"
prompt "Customer Network OPNSense WAN Subnet (ex: 24)" wan_subnet "${WAN_SUBNET}" "non-empty"
prompt "NTP Servers (Seperated by whitespace)" ntp_timeservers "${NTP_TIMESERVERS}"
prompt "NTP Primary Server (Must be in NTP Servers list)" ntp_prefer "${NTP_PREFER}"
prompt "OPNSense Base Domain Name (optionally changed)" opnsense_domain "${OPNSENSE_DOMAIN}" "non-empty"
prompt "OPNSense Hostname (optionally changed)" opnsense_hostname "${OPNSENSE_HOSTNAME}" "non-empty"
prompt "WAN Interface Device (Leave default unless custom deploy)" interface_wan "${INTERFACE_WAN}" "non-empty"
prompt "LAN Interface Device (Leave default unless custom deploy)" interface_lan "${INTERFACE_LAN}" "non-empty"
prompt "OPT1 Interface Device (Leave default unless custom deploy)" interface_opt1 "${INTERFACE_OPT1}" "non-empty"
prompt "OSDC1 MGMT MAC Address" osdc1_mac "${OSDC1_MAC}" "non-empty"


prompt "Save and Create Configuration? (yes|no)" save_config "yes" "yes|no"

if [[ $save_config == "no" ]]; then
    echo "Configuration canceled. Quiting."
    exit 0
fi

write_config_state_file
create_config_xml
