echo Vstanovlennia moduliv (mozhe tryvaty 1-3 hv)...

python.exe -m pip install --upgrade xmlschema
if errorlevel 1 goto :pip_failed
python.exe -m pip install --upgrade docxtpl
if errorlevel 1 goto :pip_failed
python.exe -m pip install --upgrade pymorphy2 pymorphy2-dicts-uk
if errorlevel 1 goto :pip_failed

echo
echo [HOTOVO] Moduli vstanovleno.
exit /b 0

:pip_failed
echo
echo [POMYLKA] Ne vdalosia vstanovyty moduli cherez pip.
echo Mozhlyvi prychyny: nema internetu, proxy/firewall, obmezheni prava.
echo Sprobuite zapustyty vid imeni administratora ta vykonaty:
echo   python-lib.bat --system
echo
exit /b 3
