echo off
rmdir dist /S /Q
mkdir dist
python -m build
python -m twine upload dist/* -u __token__ -p %OktaPyMAAPIKey%