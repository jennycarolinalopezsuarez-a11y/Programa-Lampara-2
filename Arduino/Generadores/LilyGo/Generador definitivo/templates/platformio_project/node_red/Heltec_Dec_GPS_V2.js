let p = msg.payload;

if (!p || !p.raw_data_hex) {
    return null;
}

let hex = p.raw_data_hex.trim().toUpperCase();

// Compatibilidad: mínimo 36 bytes originales.
if (hex.length < 72) {
    node.warn("Payload MinerGuard demasiado corto; mínimo 36 bytes: " + hex);
    return null;
}

function hexByte(pos) {
    return parseInt(hex.substr(pos * 2, 2), 16);
}

function readU16BE(bytePos) {
    return (hexByte(bytePos) << 8) | hexByte(bytePos + 1);
}

function readI32BE(bytePos) {
    let unsigned =
        hexByte(bytePos) * 0x1000000 +
        hexByte(bytePos + 1) * 0x10000 +
        hexByte(bytePos + 2) * 0x100 +
        hexByte(bytePos + 3);

    return unsigned >= 0x80000000
        ? unsigned - 0x100000000
        : unsigned;
}

function decodeBeacon(base) {
    let major = readU16BE(base);
    let minor = readU16BE(base + 2);
    let rssiEnc = hexByte(base + 4);
    let rssiReal = rssiEnc - 127;

    let valid = (major > 0 || minor > 0);

    return {
        valid: valid,
        major: valid ? major : 0,
        minor: valid ? minor : 0,
        rssi: valid ? rssiReal : 0
    };
}

let flags = hexByte(0);

let panic          = (flags & 0x01) !== 0;
let hr_valid       = (flags & 0x02) !== 0;
let bandbat_valid  = (flags & 0x04) !== 0;
let ble_connected  = (flags & 0x08) !== 0;
let gps_valid      = (flags & 0x10) !== 0;
let gps_active     = (flags & 0x20) !== 0; // módulo encendido/buscando

let hr_bpm       = hr_valid ? hexByte(1) : 0;
let band_battery = bandbat_valid ? hexByte(2) : 0;
let node_id      = hexByte(3) | (hexByte(4) << 8);

// Payload base original: 36 bytes.
let b1 = decodeBeacon(6);
let b2 = decodeBeacon(11);
let b3 = decodeBeacon(16);
let b4 = decodeBeacon(21);
let b5 = decodeBeacon(26);
let b6 = decodeBeacon(31);

// Extensión GPS V2: 46 bytes = 92 caracteres HEX.
let gps_payload_present = hex.length >= 92;
let latitud = null;
let longitud = null;
let gps_satelites = null;
let gps_hdop = null;

if (gps_payload_present) {
    let latE6 = readI32BE(36);
    let lonE6 = readI32BE(40);
    let sats = hexByte(44);
    let hdopX10 = hexByte(45);

    gps_satelites = sats;
    gps_hdop = hdopX10 === 255 ? null : hdopX10 / 10;

    // Solo publicar coordenadas cuando el flag confirma fix válido.
    if (gps_valid) {
        latitud = latE6 / 1000000;
        longitud = lonE6 / 1000000;
    }
}

msg.device_type = "heltec";

msg.payload_decoded = {
    timestamp: p.timestamp,
    application: p.application,
    application_id: p.application_id,
    device_name: p.device_name,
    dev_eui: p.dev_eui,
    fcnt: p.fcnt,
    fport: p.fport,
    gateway_id: p.gateway_id,
    gateway_name: p.gateway_name,
    rssi: p.rssi,
    snr: p.snr,
    frequency: p.frequency,
    sf: p.sf,
    bandwidth: p.bandwidth,
    raw_data_hex: hex,
    payload_bytes: hex.length / 2,

    flags_raw: flags,

    panic: panic,
    hr_valid: hr_valid,
    bandbat_valid: bandbat_valid,
    hr_bpm: hr_bpm,
    band_battery: band_battery,
    node_id: node_id,
    ble_connected: ble_connected,

    gps_payload_present: gps_payload_present,
    gps_active: gps_active,
    gps_valid: gps_valid,
    latitud: latitud,
    longitud: longitud,
    gps_satelites: gps_satelites,
    gps_hdop: gps_hdop,

    ["hr_" + p.device_name]: hr_bpm,

    foto_A: {
        beacon_1: b1,
        beacon_2: b2,
        beacon_3: b3
    },
    foto_B: {
        beacon_4: b4,
        beacon_5: b5,
        beacon_6: b6
    }
};

node.status({
    fill: gps_valid ? "green" : (gps_active ? "yellow" : "blue"),
    shape: gps_valid ? "dot" : "ring",
    text: gps_valid
        ? `GPS OK ${latitud}, ${longitud} | SAT ${gps_satelites} HDOP ${gps_hdop}`
        : (gps_active
            ? `GPS BUSCANDO | ${msg.payload_decoded.payload_bytes} bytes`
            : `MODO BEACON | GPS OFF | ${msg.payload_decoded.payload_bytes} bytes`)
});

return msg;