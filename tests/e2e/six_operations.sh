#!/usr/bin/env bash
# Ejecución contra producción: API_URL=... ACCESS_TOKEN=... ./tests/e2e/six_operations.sh archivo.pdf
set -euo pipefail

: "${API_URL:?Defina API_URL, por ejemplo https://d3cy0g77xzrodj.cloudfront.net}"
: "${ACCESS_TOKEN:?Defina un access token Cognito de un usuario admin}"
file=${1:?Indique el archivo que se subirá}
auth=(-H "Authorization: Bearer $ACCESS_TOKEN")
base=${API_URL%/}/api/documents
folio="E2E-$(date +%s)"

create=$(curl -fsS "${auth[@]}" -H 'Content-Type: application/json' -d "{\"folio\":\"$folio\",\"name\":\"Prueba E2E\",\"document_type\":\"application/pdf\"}" "$base")
id=$(printf '%s' "$create" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
curl -fsS "${auth[@]}" -X PUT -H 'Content-Type: application/pdf' --data-binary "@$file" "$base/$id/content" >/dev/null
curl -fsS "${auth[@]}" "$base/$id" >/dev/null
curl -fsS "${auth[@]}" "$base" >/dev/null
curl -fsS "${auth[@]}" -X PATCH -H 'Content-Type: application/json' -d '{"name":"Prueba E2E editada","status":"ACTIVE"}' "$base/$id" >/dev/null
curl -fsS "${auth[@]}" -X DELETE "$base/$id" >/dev/null
test "$(curl -s -o /dev/null -w '%{http_code}' "${auth[@]}" "$base/$id")" = 404
printf 'OK: crear, subir, listar uno/todos, editar y borrar (%s)\n' "$id"
