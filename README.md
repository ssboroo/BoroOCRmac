# BoroOCR for macOS

Монгол асуулт, сонголтыг дэлгэцийн сонгосон хэсгээс Groq vision API-аар уншуулж хариулдаг desktop програм.

## Шууд татаж ашиглах — Python шаардлагагүй

**[DMG татах / Releases](https://github.com/ssboroo/BoroOCRmac/releases/latest)**

| Mac | Файл |
| --- | --- |
| Apple Silicon, M-series | `BoroOCR-arm64.dmg` |
| Intel | `BoroOCR-x86_64.dmg` |

macOS **15 буюу шинэ** хувилбарт зориулсан. Build бүр macOS runner дээр үүснэ.
Эхний build хараахан дуусаагүй бол [Actions](https://github.com/ssboroo/BoroOCRmac/actions)-ийг харна уу.

1. DMG нээгээд **BoroOCR.app → Applications** руу чирнэ.
2. Applications дотроос програмаа нээнэ.
3. Энэ build Apple Developer ID / notarization-гүй. macOS хаавал **System Settings → Privacy & Security → Open Anyway** ашиглана.
4. **Хэсэг сонгох** дарж Screen Recording зөвшөөрөл өгөөд програмаа бүрэн хааж дахин нээнэ.
5. Үндсэн дэлгэцийн асуулт + сонголтыг хүрээлнэ. Програмын цонхоо сонгосон хүрээнээс гадна байрлуулна.
6. **Хяналт эхлүүлэх** дарж өөрийн [Groq API key](https://console.groq.com/keys) оруулна.

Python, pip, Terminal хэрэглэгчид шаардлагагүй. Интернэт болон Groq API эрх шаардлагатай.

## Боломж ба хязгаар

- Retina 1x/2x координатын хөрвүүлэлт.
- Дэлгэцийн хэсэг тогтворжиж, өөрчлөгдөхөд дараагийн асуултыг автоматаар шинжилнэ.
- Өмнөх хариулт цонхонд үлдэнэ; програм хаахад түүх арилна.
- API хүсэлт background thread дээр ажиллана.
- API key эх кодод болон дискэнд хадгалагдахгүй; зөвхөн санах ойд байна.
- Сонгосон зургийг Groq руу илгээнэ. Бүх дэлгэцийг локал санах ойд авч, хүрээг тайрсны дараа илгээнэ.
- Үндсэн дэлгэц дэмжинэ. Дэлгэцийн тохиргоо өөрчилбөл хэсгээ дахин сонгоно.
- Хариултын үнэн зөв байдал, 10 секундэд хариулахыг батлахгүй. Rate limit үед 10 секунд хүлээж нийт 3 удаа оролдоно.
- Зогсоох нь шинэ хүсэлт илгээхийг зогсооно; ажиллаж буй хүсэлт дуусаж болно.

## Build ба шалгалт

Main руу push хийхэд эсвэл Actions → Build macOS DMG → Run workflow ажиллуулахад:

1. Apple Silicon ба Intel macOS runner тус бүрт эх код болон Tk UI startup шалгана.
2. PyInstaller-аар Python, Tcl/Tk, Pillow, OpenAI SDK агуулсан `.app` багцална.
3. **Багцалсан executable**-ийг нээж UI/Tk, Retina crop, зураг encode, SDK import шалгана. API key, сүлжээ, дэлгэцийн зөвшөөрөл шаардахгүй.
4. Ad-hoc signature болон DMG бүтцийг шалгана.
5. Хоёр build амжилттай бол DMG, SHA-256 файлыг GitHub Release-д нийтэлнэ.

Энэ автомат шалгалт нь хэрэглэгчийн Screen Recording зөвшөөрөл, бодит дэлгэцийн capture эсвэл амьд Groq хариултын end-to-end баталгаа биш.

### Хөгжүүлэгчийн локал build (зөвхөн Mac)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt 'pyinstaller>=6.11,<7'
bash scripts/build_macos.sh
```

Tkinter агуулсан Python 3.12 ашиглана. Өөрийн Mac-ийн architecture-д build хийнэ.
Apple-ийн баталгаажуулсан түгээлт хийх бол Developer ID certificate болон notarization credentials-ийг тусад нь тохируулах шаардлагатай; энэ repository-д нууц түлхүүр оруулахгүй.
