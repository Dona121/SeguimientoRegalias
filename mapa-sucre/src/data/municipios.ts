// Tabla maestra de los 26 municipios de Sucre (§5 de la guía).
// code = MPIO_CDPMP (DANE, texto de 5 dígitos, prefijo 70).
// nombre = MPIO_CNMBR (nombre oficial DANE, con tildes; para mostrar).
// lat/lng = centroide de la cabecera municipal (para marcadores).
export interface Municipio {
  code: string;
  nombre: string;
  lat: number;
  lng: number;
}

export const MUNICIPIOS: Municipio[] = [
  { code: "70001", nombre: "SINCELEJO", lat: 9.3047, lng: -75.3978 },
  { code: "70110", nombre: "BUENAVISTA", lat: 9.3197, lng: -74.9706 },
  { code: "70124", nombre: "CAIMITO", lat: 8.7892, lng: -75.1144 },
  { code: "70204", nombre: "COLOSÓ", lat: 9.4961, lng: -75.3531 },
  { code: "70215", nombre: "COROZAL", lat: 9.3211, lng: -75.2939 },
  { code: "70221", nombre: "COVEÑAS", lat: 9.4011, lng: -75.6800 },
  { code: "70230", nombre: "CHALÁN", lat: 9.5450, lng: -75.3147 },
  { code: "70233", nombre: "EL ROBLE", lat: 9.1014, lng: -75.1003 },
  { code: "70235", nombre: "GALERAS", lat: 9.1639, lng: -75.0497 },
  { code: "70265", nombre: "GUARANDA", lat: 8.4675, lng: -74.5378 },
  { code: "70400", nombre: "LA UNIÓN", lat: 8.8500, lng: -75.2833 },
  { code: "70418", nombre: "LOS PALMITOS", lat: 9.3792, lng: -75.2675 },
  { code: "70429", nombre: "MAJAGUAL", lat: 8.5419, lng: -74.6286 },
  { code: "70473", nombre: "MORROA", lat: 9.3406, lng: -75.3097 },
  { code: "70508", nombre: "OVEJAS", lat: 9.5247, lng: -75.2294 },
  { code: "70523", nombre: "PALMITO", lat: 9.3372, lng: -75.5358 },
  { code: "70670", nombre: "SAMPUÉS", lat: 9.1814, lng: -75.3814 },
  { code: "70678", nombre: "SAN BENITO ABAD", lat: 8.9311, lng: -75.0339 },
  { code: "70702", nombre: "SAN JUAN DE BETULIA", lat: 9.2667, lng: -75.2417 },
  { code: "70708", nombre: "SAN MARCOS", lat: 8.6597, lng: -75.1330 },
  { code: "70713", nombre: "SAN ONOFRE", lat: 9.7361, lng: -75.5283 },
  { code: "70717", nombre: "SAN PEDRO", lat: 9.3956, lng: -75.0567 },
  { code: "70742", nombre: "SAN LUIS DE SINCÉ", lat: 9.2433, lng: -75.1450 },
  { code: "70771", nombre: "SUCRE", lat: 8.8094, lng: -74.7211 },
  { code: "70820", nombre: "SANTIAGO DE TOLÚ", lat: 9.5236, lng: -75.5828 },
  { code: "70823", nombre: "SAN JOSÉ DE TOLUVIEJO", lat: 9.4500, lng: -75.4400 },
];

// Aliases coloquiales → nombre DANE normalizado (§6.3). Las claves ya están
// normalizadas (mayúsculas, sin tildes). Amplía esta tabla cuando el usuario
// confirme un nombre que hoy no se resuelve.
export const ALIAS: Record<string, string> = {
  "SINCE": "SAN LUIS DE SINCE",
  "SAN LUIS SINCE": "SAN LUIS DE SINCE",
  "TOLU": "SANTIAGO DE TOLU",
  "TOLU VIEJO": "SAN JOSE DE TOLUVIEJO",
  "TOLUVIEJO": "SAN JOSE DE TOLUVIEJO",
  "SAN ANTONIO DE PALMITO": "PALMITO",
};

// Centinela de cobertura departamental (§6.5).
export const SENTINEL_TODO_DEPTO = "TODO EL DEPARTAMENTO DE SUCRE";
