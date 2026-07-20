// =======================================================
// MAPEAR DATOS HELTEC A HR1...HR20
// Salida:
// msg.modbus_mapping = { hr1, hr2, ..., hr20 }
// msg.payload = [hr1, hr2, ..., hr20]
//
// Convención beacons:
// Major = nivel
// Minor = PK
// RSSI  = intensidad de señal
// =======================================================

let d = msg.payload_decoded || {};
let t = msg.trayectoria || {};

function numero(valor, defecto = null) {
    if (valor === undefined || valor === null || valor === "") return defecto;
    let n = Number(valor);
    return isNaN(n) ? defecto : n;
}

function boolToInt(v) {
    return v ? 1 : 0;
}

function tomar(...valores) {
    for (let v of valores) {
        if (v !== undefined && v !== null && v !== "") {
            return v;
        }
    }
    return null;
}

// Validación
if (!d || !d.node_id) {
    node.warn("No existe msg.payload_decoded.node_id. No se puede mapear HR.");
    node.warn(msg);
    return null;
}

// =======================================================
// SNR x10
// =======================================================

let snr_x10 = null;

if (d.snr !== undefined && d.snr !== null) {
    snr_x10 = Math.round(Number(d.snr) * 10);
}

// =======================================================
// RSSI de beacons actuales
// Foto B = lectura más actual.
// Si no hay beacons prendidos, quedarán NULL.
// =======================================================

let bc1_rssi = tomar(
    d.foto_B && d.foto_B.beacon_4 && d.foto_B.beacon_4.valid
        ? d.foto_B.beacon_4.rssi
        : null
);

let bc2_rssi = tomar(
    d.foto_B && d.foto_B.beacon_5 && d.foto_B.beacon_5.valid
        ? d.foto_B.beacon_5.rssi
        : null
);

let bc3_rssi = tomar(
    d.foto_B && d.foto_B.beacon_6 && d.foto_B.beacon_6.valid
        ? d.foto_B.beacon_6.rssi
        : null
);

// =======================================================
// BEACON MÁS FUERTE
// Major = nivel
// Minor = PK
// RSSI  = intensidad
// =======================================================

function obtenerBeaconMasFuerte(d) {
    let beacons = [];

    function agregarBeacons(foto) {
        if (!foto) return;

        for (let k in foto) {
            let b = foto[k];

            if (b && b.valid && b.rssi !== 0) {
                beacons.push({
                    major: Number(b.major),
                    minor: Number(b.minor),
                    rssi: Number(b.rssi)
                });
            }
        }
    }

    // Foto B es la actual, Foto A queda como respaldo
    agregarBeacons(d.foto_B);
    agregarBeacons(d.foto_A);

    if (beacons.length === 0) return null;

    // RSSI más alto = señal más fuerte.
    // Ejemplo: -45 es más fuerte que -80.
    beacons.sort((a, b) => b.rssi - a.rssi);

    return beacons[0];
}

let beaconFuerte = obtenerBeaconMasFuerte(d);

// Major del beacon más fuerte.
// También toma el dato del Filtro Kalman si ya lo calculó.
let major_actual = tomar(
    t.major_actual,
    t.nivel_actual,
    beaconFuerte ? beaconFuerte.major : null
);

// Minor del beacon más fuerte, por respaldo/debug.
let minor_actual = tomar(
    t.minor_actual,
    t.pk_beacon_mas_fuerte,
    beaconFuerte ? beaconFuerte.minor : null
);

// RSSI del beacon más fuerte, por respaldo/debug.
let rssi_beacon_mayor = tomar(
    t.rssi_beacon_mayor,
    beaconFuerte ? beaconFuerte.rssi : null
);

// =======================================================
// HR1 a HR20
// =======================================================

let hr = {
    // HR1 a HR10 → historico_dispositivos
    hr1: numero(d.node_id, null),                         // id_dispositivo
    hr2: d.hr_valid ? numero(d.hr_bpm, null) : null,      // heart_rate
    hr3: boolToInt(d.panic),                              // panico
    hr4: numero(t.posicion_actual, null),                 // posicion_actual
    hr5: numero(t.posicion_anterior, null),               // posicion_anterior
    hr6: numero(t.posicion_futura, null),                 // posicion_futura
    hr7: numero(d.latitud, null),                         // latitud
    hr8: numero(d.longitud, null),                        // longitud
    hr9: numero(d.bateria_tag, null),                     // bateria_tag

    // CAMBIO PRINCIPAL:
    // Antes HR10 guardaba el RSSI más fuerte.
    // Ahora HR10 guarda el MAJOR del beacon más fuerte.
    // En SQL esto se guarda en historico_dispositivos.mayor.
    // Convención: Major = nivel.
    hr10: numero(major_actual, null),                     // nivel / major beacon

    // HR11 a HR20 → estado_actual_dispositivos
    hr11: boolToInt(d.ble_connected),                     // banda_conectada
    hr12: d.bandbat_valid ? numero(d.band_battery, null) : null, // bateria_banda
    hr13: numero(d.rssi, null),                           // rssi_lorawan
    hr14: numero(snr_x10, null),                          // snr_x10
    hr15: numero(d.fcnt, null),                           // fcnt
    hr16: numero(d.flags_raw, null),                      // flags
    hr17: numero(bc1_rssi, null),                         // bc1_rssi
    hr18: numero(bc2_rssi, null),                         // bc2_rssi
    hr19: numero(bc3_rssi, null),                         // bc3_rssi
    hr20: boolToInt(d.gps_valid)                         // GPS: 0=NO, 1=SI
};

// =======================================================
// CAMPOS DE RESPALDO / DEBUG
// =======================================================

msg.gps = {
    valido: boolToInt(d.gps_valid),
    payload_presente: !!d.gps_payload_present,
    latitud: numero(d.latitud, null),
    longitud: numero(d.longitud, null),
    satelites: numero(d.gps_satelites, null),
    hdop: numero(d.gps_hdop, null)
};

msg.modbus_mapping = hr;

msg.nivel_actual = numero(major_actual, null);
msg.major_actual = numero(major_actual, null);
msg.minor_actual = numero(minor_actual, null);
msg.pk_beacon_mas_fuerte = numero(minor_actual, null);
msg.rssi_beacon_mayor = numero(rssi_beacon_mayor, null);

// Payload como arreglo HR1...HR20
msg.payload = [
    hr.hr1,
    hr.hr2,
    hr.hr3,
    hr.hr4,
    hr.hr5,
    hr.hr6,
    hr.hr7,
    hr.hr8,
    hr.hr9,
    hr.hr10,
    hr.hr11,
    hr.hr12,
    hr.hr13,
    hr.hr14,
    hr.hr15,
    hr.hr16,
    hr.hr17,
    hr.hr18,
    hr.hr19,
    hr.hr20
];

node.status({
    fill: "green",
    shape: "dot",
    text: `ID ${hr.hr1} | GPS ${hr.hr20} | LAT ${hr.hr7 ?? "-"} | LON ${hr.hr8 ?? "-"}`
});

return msg;