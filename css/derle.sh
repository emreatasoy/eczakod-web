#!/bin/sh
# site.css parçalardan üretilir; parçayı düzenleyip bunu çalıştırın.
cd "$(dirname "$0")" && cat fonts.part main.part ana.part kurulum.part iletisim.part > site.css
