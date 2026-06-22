.PHONY: install serve plates photos photos-transparent enrich
install:
	pip install -r requirements.txt
	npm install
serve:
	@echo "Open http://localhost:8000  (Ctrl-C to stop)"
	python3 -m http.server 8000
plates:
	python3 scripts/fishgen.py
photos:
	python3 scripts/fishgen_photo.py
photos-transparent:
	python3 scripts/fishgen_photo.py --transparent
enrich:
	node scripts/enrich.mjs
