TOKEN=$(getjwt test)
ENDPOINTS=(
    "/api/v1/system/device/info"
    "/api/v1/system/device/stats"
    "/api/v1/system/service/status?name=kismet"
    "/api/v1/bluetooth/status"
    "/api/v1/network/interfaces"
    "/api/v1/network/wlan/getInterfaces"
    "/api/v1/network/info/"
    "/api/v1/utils/reachability"
    "/api/v1/utils/usb"
    "/api/v1/utils/ufw"
    "/api/v1/system/timezone"
    "/api/v1/system/timezone/list"
    "/api/v1/system/reg-domain"
    "/api/v1/system/updates"
    "/api/v1/system/battery"
    "/api/v1/system/datetime"
    "/api/v1/system/ssid-passphrase"
    "/api/v1/system/clients"
    "/api/v1/network/info/publicip6"
    "/api/v1/profiler/status"
)

for endpoint in "${ENDPOINTS[@]}"; do
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $TOKEN" "http://localhost:31415$endpoint")
    if [[ "$STATUS" == "4"* ]] || [[ "$STATUS" == "5"* ]]; then
        echo "ERROR: $endpoint returned $STATUS"
        # Print the actual body
        curl -s -H "Authorization: Bearer $TOKEN" "http://localhost:31415$endpoint"
        echo ""
    else
        echo "OK: $endpoint returned $STATUS"
    fi
done
