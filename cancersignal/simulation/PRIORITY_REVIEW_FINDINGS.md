# Priorisoitu etätarkistus ja pitchin mittarit

Muutokset on tehty erilliseen `feat/simulation-real-model`-työpuuhun. Simulaatio on nyt kansiossa `cancersignal/simulation/`. Main-työpuun keskeneräiseen demo-, backend- tai frontend-työhön ei koskettu. Tässä muutoksessa ei tehty uusia mallikutsuja eikä backend-muutoksia; aiemmin hyväksytty yhden importin korjaus säilyy erillisessä työpuussa.

## Mitä korjattiin

- Lääkärin etätarkistus käyttää yhteistä lääkärikapasiteettia prioriteettijonossa. Oikean ennusteen `urgent` käsitellään ennen muuta tarkistusta, muut tarkistukset ennen odottavaa tavallista vastaanottoa. Käynnissä olevaa työtä ei keskeytetä. Samantasoiset pyynnöt ovat saapumisjärjestyksessä. Todellinen myöhemmän päätöshetken kiireellisyys toimii samoin.
- Oletuskapasiteetti nostettiin 2:sta 3:een molemmissa vertailuhaaroissa. Tämä on järjestelmän oletus, ei CancerSignalin tuottama kapasiteettihyöty. Vanha kahden kapasiteetin kuormitustapaus säilyy, samoin FIFO ja alkuperäinen B-polku.
- `run` käyttää oletuksena A/C-vertailua. Jo lääkärin aiheelliseksi arvioima tutkimus ei odota erillistä AI-tarkistusta. Vanha B-valinta ja kaikki sen tapahtumaregressiot säilyvät alkuperäisellä asetustiedostolla.
- Päämittarit ovat 30/60 päivässä valmistunut ensimmäinen tutkimus, lisätyt ja menetetyt valmistumiset, ilman valmistunutta tutkimusta 30 päivänä olevien osuus sekä P90. Mukana ovat myös GP-kuormitus ja vertailuluokitukseltaan negatiivisten tutkimukset.

P90 on aikajakauman 90. prosenttipiste, ei pitkään odottaneiden osuus. Pelkkä tutkimuksiin päässeiden P90 jättää muut pois. Siksi mukana on myös 60 päivään rajattu P90: valmistumatta jääneiden arvo on 60. Jokaisella päämittarien potilaalla on kokonainen 60 päivän havaintoikkuna.

## Ajettu vertailu

Neljä asetusta × 30 yhteisin satunnaissiemenin paritettua toistoa × A/B/C/D = 480 hypoteettista skenaarioajoa. Sama potilasjoukko, kapasiteetti ja satunnaisluvut jokaisen asetuksen sisällä. Lisäksi oikean mallin 33 tapauksen A/C/D-uusinta ja saman joukon hypoteettinen vertailu: 180 ajoa ilman uusia LLM-kutsuja.

Luvut alla ovat 30 toiston keskiarvoja. Tässä väestöajossa herkkyys 80 % ja väärien hälytysten osuus 12 % ovat yhä oletuksia. Oikeiden malliennusteiden tulos raportoidaan erikseen.

| Asetus | A: tutkimus valmis 60 pv | C: tutkimus valmis 60 pv | A: GP-käyttöaste |
|---|---:|---:|---:|
| 2 kapasiteettia, fifo | 76.11 % | 85.53 % | 100.00 % |
| 2 kapasiteettia, priority | 76.11 % | 88.29 % | 100.00 % |
| 3 kapasiteettia, fifo | 90.28 % | 94.93 % | 87.61 % |
| 3 kapasiteettia, priority | 90.28 % | 94.93 % | 87.61 % |

Kolmen kapasiteetin priorisoidussa asetuksessa tutkimus valmistui keskimäärin 146,6 → 154,2 tapaukselle 162,4 vertailupositiivisesta. Lisäys oli 7,6 tapausta; menetettyjä 60 päivän valmistumisia ei näissä toistoissa havaittu. Kattavuuden ero oli +4,65 prosenttiyksikköä (Monte Carlo -95 % väli +4,02…+5,29). Tämä ei ole kliinisen vaikutuksen luottamusväli.

Ilman valmistunutta tutkimusta 30 päivänä oli 9,7 % → 5,1 %. Rajattu P90 oli 34,17 → 21,94 päivää; vain valmistuneista laskettu P90 21,89 → 21,74 päivää. Jälkimmäinen peittäisi suuren osan kattavuushyödystä. Vertailunegatiivisten tutkimuksia tuli 190,0 → 247,1 tuhatta vastaavaa tapausta kohden, joten lisätutkimusten haitta ei häviä.

Priorisointi yksin ei parantanut kolmen kapasiteetin asetuksen 60 päivän kattavuutta FIFOon nähden: molemmissa C oli 94,93 %. Sen sijaan kahden kapasiteetin ylikuormituksessa vaikutus oli suurempi. Etusija siirtää työtä jonossa; se ei korjaa kapasiteettivajetta. Ylikuormitetun B/FIFO-haaran 30 päivän valmistumiset olivat lähtötilaa heikommat, ja tämä tulos on mukana raportissa.

Lähtötilan oletettu GP-työkuorma vanhalla automaattisen kontrollin reitityksellä on noin `12 × 0,12 × (2 − (0,15 × 0,55 + 0,85 × 0,12)) = 2,614` kapasiteettiyksikköä. Kahdella käyttöasteen teoreettinen tarve ylittää 100 %, kolmella se on noin 87 %. Mitattu lähtötilan käyttöaste oli 87,6 % ja jonon kasvunopeus 0,011 potilasta/päivä, kun kahdella kasvu oli 3,50. Äärellinen 180 päivän koe ei yksin todista todellisen terveydenhuoltojärjestelmän tasapainoa.

## Oikeiden ennusteiden uusinta

Samat 33 validoitua CancerSignal-ennustetta: A 71,48 %, C 86,67 %, D 82,59 % valmistuneita 60 päivässä. Tulos ei muuttunut aiemmasta FIFO/two-capacity-ajosta. GP-käyttöaste jäi noin 1,1 prosenttiin, joten tässä aineistossa jonoprioriteetilla ei ole merkittävää vaikutusta. Kaikki kolme alkuperäistä ennustevirhettä säilyvät arvioinnissa näkyvissä; niitä ei korvattu satunnaissignaalilla.

Tämä aineisto on erillinen synteettinen arviointijoukko, ei sovelluksen uudempi demopotilasjoukko. Tavallinen väestödemo puolestaan generoi potilaat eikä lue automaattisesti vanhaa seediä. Vanha seed-adapteri on vain erikseen valittava työkalu. Tapausten uudelleennimeäminen demopotilaiksi tai syöpäpotilaiksi olisi harhaanjohtavaa.

## Pitchiin sopiva rajattu ilmaisu

> Hypoteettisessa, samalla kapasiteetilla tehdyssä simulaatiossa ei-estävä CancerSignal-tarkistus nosti tutkimuksen 60 päivässä saavuttaneiden vertailupositiivisten tapausten osuuden 90,3 prosentista 94,9 prosenttiin. Samalla muiden tapausten tutkimusmäärä kasvoi. Tämä ei ole mitattu kliininen vaikutus.

Oikeilla ennusteilla tehdyn demon voi esitellä erikseen end-to-end-toimivuuden näyttönä. Se ei osoita ruuhkautuneen järjestelmän hyötyä eikä riippumatonta syövän tunnistustarkkuutta. Aineiston vertailuluokat perustuvat samaan sääntökirjaan; ulkopuolinen kliininen validointi puuttuu.

## Tarkistus ja aineistot

49 testiä läpäisty, mukaan lukien priorisointi, käynnissä olevan vastaanoton suojaaminen, muille potilaille syntyvä viive, tuntemattoman asetuksen hylkäys, puuttuvien tutkimusten sisällyttäminen P90:een sekä alkuperäinen A/B-tapahtumaregressio. Oletus-CLI ja kuva tuotettu ja tarkastettu. Backend ja frontend eivät muuttuneet tässä korjauksessa.

- [Kaikki vertailutaulukot](results/priority_review/REPORT.md)
- `results/priority_review/gp*_*.json`: jokainen toisto, asetukset, päämittarit, paritetut erot ja välit.
- `results/priority_review/real_model/`: uusi oikeiden ennusteiden vertailu ja potilaspolut.
- `results/priority_review/demo_5_seeds.png`: oletus-CLI:n erillinen viiden siemenen havainnekuva; ei yllä olevan 30 toiston taulukon kuva.
- Ensimmäisten toistojen täydet tapahtumalokit: `outputs/pitch_review/sample_runs/`.
- [Ajokomennot ja oletukset](README.md). Vanhojen raporttien tuloksia ei korvattu uusilla samoihin tiedostoihin.

Muutoksia ei ole commitattu, pushattu tai yhdistetty mainiin.
