"""Year inference from chip model/name — priority-ordered regex chain.

Priority chain (checked in order, first match wins):

1.  MediaTek MT\\d{4} model pattern
2.  MediaTek DIMENSITY / HELIO pattern
3.  HiSilicon Kirin pattern
4.  Qualcomm SM/SDM pattern
5.  Qualcomm MSM/APQ pattern
6.  Samsung Exynos pattern
7.  Qualcomm Snapdragon X Elite/Plus
8.  Qualcomm Snapdragon X2
9.  Qualcomm Snapdragon N Gen M (N-series + generation)
10. Rockchip RK\\d{4}
11. Allwinner A/M prefix pattern
12. Nvidia Tegra pattern
13. Intel T-prefix pattern
14. Tegra X1 pattern (TE\\d{3}X1 / T\\d{3}X1)
15. Intel Atom Z/N/x prefix (no year assignment — fall through)
16. Intel x/zn prefix pattern
17. Qualcomm G-series Gen N pattern
18. Qualcomm G-series X Gen N pattern
19. Microsoft SQ pattern
20. Qualcomm QCS pattern
21. Qualcomm SC pattern
22. Qualcomm SA pattern
23. Qualcomm WEAR pattern
24. Qualcomm W-series Gen N pattern
25. Qualcomm XR pattern
26. Snapdragon 3-digit pattern
27. Qualcomm QSD pattern
28. Qualcomm SW pattern
29. Qualcomm CE pattern
30. TI OMAP pattern
31. Allwinner/HiSilicon/Rockchip A/H/F/R prefix pattern
32. Amlogic S-prefix pattern
33. Amlogic T-prefix (vendor-gated)
34. MediaTek Kompanio pattern
35. Intel Atom D/N pattern
36. Ingenic JZ pattern
37. Qualcomm THOR pattern
38. Allwinner F1C/F1E pattern
39. Qualcomm AIOT I pattern
40. Spreadtrum SP pattern
41. Qualcomm UMS pattern
42. HiSilicon K3V2 pattern
43. HiSilicon Kirin T-prefix pattern
"""

from __future__ import annotations

import re
from typing import Any


def infer_year(chip: dict[str, Any]) -> int | None:
    """Infer release year from chip model/name.

    Implements the priority-ordered regex chain documented in the module docstring.
    The first matching pattern wins. Returns ``None`` if no pattern matches.

    Args:
        chip: The chip record with model and name fields.

    Returns:
        The inferred year as ``int``, or ``None`` if no pattern matched.
    """
    year: int | None = None
    for f_text in (chip.get("model", "").upper(), chip.get("name", "").upper()):
        if not f_text:
            continue
        # 1. MediaTek MT\d{4}
        m = re.search(r"MT(\d{4})", f_text)
        if m:
            mt_val = int(m.group(1))
            if mt_val >= 9900:
                year = 2025
            elif mt_val >= 9800:
                year = 2024
            elif mt_val >= 9200:
                year = 2023
            elif mt_val >= 8700:
                year = 2022
            elif mt_val >= 8300:
                year = 2021
            elif mt_val >= 8000:
                year = 2020
            elif mt_val >= 7900:
                year = 2019
            elif mt_val >= 7500:
                year = 2018
            elif mt_val >= 7000:
                year = 2017
            elif mt_val >= 6500:
                year = 2016
            elif mt_val >= 6000:
                year = 2015
            elif mt_val >= 5000:
                year = 2014
            else:
                year = 2013
            break
        # 2. MediaTek DIMENSITY/HELIO
        m = re.search(r"(?:DIMENSITY|HELIO)\s*(\d{3,4})", f_text)
        if m:
            d = int(m.group(1))
            if d >= 9400:
                year = 2025
            elif d >= 9300 or d >= 9200:
                year = 2024
            elif d >= 9000:
                year = 2023
            elif d >= 8400 or d >= 8300:
                year = 2024
            elif d >= 8200:
                year = 2023
            elif d >= 8100 or d >= 8000:
                year = 2022
            elif d >= 7200:
                year = 2023
            elif d >= 7000 or d >= 6000:
                year = 2022
            elif d >= 1200 or d >= 1100:
                year = 2021
            elif d >= 1000:
                year = 2020
            elif d >= 900:
                year = 2019
            elif d >= 800:
                year = 2018
            elif d >= 700:
                year = 2017
            elif d >= 600:
                year = 2016
            elif d >= 500:
                year = 2015
            else:
                year = 2014
            break
        # 3. HiSilicon Kirin
        m = re.search(r"KIRIN\s*(\d{3,4})", f_text)
        if m:
            kirin = int(m.group(1))
            if kirin >= 9010:
                year = 2024
            elif kirin >= 9000:
                year = 2020
            elif kirin >= 8000:
                year = 2024
            elif kirin >= 990:
                year = 2019
            elif kirin >= 980:
                year = 2018
            elif kirin >= 970:
                year = 2017
            elif kirin >= 960:
                year = 2016
            elif kirin >= 950 or kirin >= 930:
                year = 2015
            elif kirin >= 920 or kirin >= 900:
                year = 2014
            elif kirin >= 800 or kirin >= 700:
                year = 2018
            elif kirin >= 600:
                year = 2015
            else:
                year = 2013
            break
        # 4. Qualcomm SM/SDM
        m = re.search(r"(?:SM|SDM)(\d{3,4})", f_text)
        if m:
            sm = int(m.group(1))
            if sm >= 8750:
                year = 2025
            elif sm >= 8650:
                year = 2024
            elif sm >= 8550:
                year = 2023
            elif sm >= 8450:
                year = 2022
            elif sm >= 8350:
                year = 2021
            elif sm >= 8250:
                year = 2020
            elif sm >= 8150:
                year = 2019
            elif sm >= 8000:
                year = 2018
            elif sm >= 7000:
                year = 2017
            elif sm >= 6000:
                year = 2016
            elif sm >= 5000:
                year = 2015
            elif sm >= 4000:
                year = 2014
            elif sm >= 3000:
                year = 2013
            elif sm >= 2000:
                year = 2012
            else:
                year = 2011
            break
        # 5. Qualcomm MSM/APQ
        m = re.search(r"(?:MSM|APQ)(\d{4})", f_text)
        if m:
            msm = int(m.group(1))
            if msm >= 9000:
                year = 2018
            elif msm >= 8998:
                year = 2017
            elif msm >= 8996:
                year = 2016
            elif msm >= 8994:
                year = 2015
            elif msm >= 8974:
                year = 2013
            elif msm >= 8960:
                year = 2012
            elif msm >= 8900:
                year = 2011
            elif msm >= 8200:
                year = 2010
            elif msm >= 7600:
                year = 2009
            elif msm >= 7200:
                year = 2008
            else:
                year = 2007
            break
        # 6. Samsung Exynos
        m = re.search(r"EXYNOS", f_text)
        if m:
            all_nums = re.findall(r"(\d{4})", f_text[m.end() :])
            if all_nums:
                ex = int(all_nums[0])
                if ex >= 2500:
                    year = 2025
                elif ex >= 2400:
                    year = 2024
                elif ex >= 2200:
                    year = 2022
                elif ex >= 2100:
                    year = 2021
                elif ex >= 2000:
                    year = 2020
                elif ex >= 1580:
                    year = 2025
                elif ex >= 1480:
                    year = 2024
                elif ex >= 1380:
                    year = 2023
                elif ex >= 1280:
                    year = 2022
                elif ex >= 1080:
                    year = 2020
                else:
                    year = 2005
                break
            all_3 = re.findall(r"(\d{3})", f_text[m.end() :])
            if all_3:
                ex3 = int(all_3[0])
                year = 2020 if ex3 >= 990 or ex3 >= 980 or ex3 >= 880 or ex3 >= 850 else 2015
                break
            m_w = re.search(r"EXYNOS\s+W(\d+)", f_text)
            if m_w:
                w = int(m_w.group(1))
                year = 2023 if w >= 930 else 2020
                break
            m_a = re.search(r"EXYNOS\s+AUTO\s*V(\d+)", f_text)
            if m_a:
                av = int(m_a.group(1))
                year = 2023 if av >= 920 else 2020
                break
        # 7. Qualcomm Snapdragon X Elite/Plus
        m = re.search(r"SNAPDRAGON\s*X\s*(?:ELITE|PLUS)", f_text)
        if m and not re.search(r"X\s*2", f_text):
            year = 2024
            break
        # 8. Qualcomm Snapdragon X2
        m = re.search(r"SNAPDRAGON\s*X\s*2", f_text)
        if m:
            year = 2025
            break
        # 9. Qualcomm Snapdragon N Gen M
        m = re.search(r"SNAPDRAGON\s*(\d+)\s*GEN\s*(\d+)", f_text)
        if m:
            series = int(m.group(1))
            gen = int(m.group(2))
            year = 2021 + gen if series >= 8 else 2020 + gen
            break
        # 10. Rockchip RK\d{4}
        m = re.search(r"RK(\d{4})", f_text)
        if m:
            rk = int(m.group(1))
            year = 2008 + (rk - 2000) // 200
            break
        # 11. Allwinner A/M prefix
        m = re.search(r"\b([AM])(\d+)\b", f_text)
        if m:
            prefix = m.group(1)
            num = int(m.group(2))
            if prefix == "A":
                if num >= 18:
                    year = 2025
                elif num == 17:
                    year = 2024
                elif num == 16:
                    year = 2023
                elif num == 15:
                    year = 2022
                elif num == 14:
                    year = 2020
                elif num == 13:
                    year = 2019
                elif num == 12:
                    year = 2018
                elif num == 11:
                    year = 2017
                elif num == 10:
                    year = 2016
                elif num == 9:
                    year = 2015
                elif num == 8:
                    year = 2014
                elif num == 7:
                    year = 2013
                else:
                    year = 2011 + num - 5
            elif prefix == "M":
                if num >= 4:
                    year = 2025
                elif num == 3:
                    year = 2023
                elif num == 2:
                    year = 2022
                elif num == 1:
                    year = 2020
            break
        # 12. Nvidia Tegra
        m = re.search(r"TEGRA\s*(\d+)", f_text)
        if m:
            t = int(m.group(1))
            year = 2008 + t
            break
        # 13. Intel T-prefix
        m = re.search(r"\bT([01]\d{2}|20[0-9])\b", f_text)
        if m:
            year = 2008 + int(m.group(1)[:2])
            break
        # 14. Tegra X1 (TE/T pattern)
        x1_match = re.search(r"(?:TE|T)\d{3}X1", f_text)
        if x1_match:
            year = 2015
            break
        # 15. Intel Atom (no year set — fallthrough)
        m = re.search(r"ATOM\s*(\w+)", f_text)
        if m:
            atom_name = m.group(1).upper()
            if re.search(r"Z\d{3,}", atom_name) or re.search(r"N\d{3,}", atom_name) or re.search(r"x\d{2,}", atom_name):
                pass
        # 16. Intel x/zn prefix
        m = re.search(r"\b[xzzn]\d+", f_text, re.IGNORECASE)
        if m:
            if re.search(r"[xX]\d", f_text):
                year = 2015
            elif re.search(r"[Zz]\d{4}", f_text):
                year = 2014
        # 17. Qualcomm G-series Gen N
        m = re.search(r"\bG(\d+)\s*GEN\s*(\d+)", f_text)
        if m:
            g_series = int(m.group(1))
            g_gen = int(m.group(2))
            if g_series == 1:
                year = 2020 + g_gen
            elif g_series == 3:
                year = 2022 + g_gen - 1 if g_gen >= 3 else 2021
            else:
                year = 2020 + g_gen + (g_series > 1)
            break
        # 18. Qualcomm G-series X Gen N
        m = re.search(r"\bG(\d+)X\s*GEN\s*(\d+)", f_text)
        if m:
            g_gen = int(m.group(2))
            year = 2020 + g_gen if g_gen == 1 else 2021 + g_gen
            break
        # 19. Microsoft SQ
        m = re.search(r"MICROSOFT\s+SQ(\d+)", f_text)
        if m:
            sq = int(m.group(1))
            year = 2018 + sq
            break
        # 20. Qualcomm QCS
        m = re.search(r"\bQCS(\d{3})\b", f_text)
        if m:
            qcs = int(m.group(1))
            year = 2015 + (qcs // 100)
            break
        # 21. Qualcomm SC
        m = re.search(r"\bSC(\d{4})", f_text)
        if m:
            sc = int(m.group(1))
            if sc >= 8380:
                year = 2022
            elif sc >= 8280:
                year = 2021
            elif sc >= 8180:
                year = 2019
            elif sc >= 7280:
                year = 2021
            elif sc >= 7180:
                year = 2020
            else:
                year = 2018
            break
        # 22. Qualcomm SA
        m = re.search(r"\bSA(\d{4})P?\b", f_text)
        if m:
            sa = int(m.group(1))
            if sa >= 8295:
                year = 2021
            elif sa >= 8255:
                year = 2024
            elif sa >= 8195 or sa >= 8155 or sa >= 6155:
                year = 2019
            else:
                year = 2018
            break
        # 23. Qualcomm WEAR
        m = re.search(r"WEAR\s*(\d+)", f_text)
        if m:
            wear = int(m.group(1))
            year = 2016 + (wear - 2100) // 500 if wear >= 2100 else 2018 + (wear - 2500) // 500
            year = 2020
            break
        # 24. Qualcomm W-series Gen N
        m = re.search(r"W\d+\+?\s*GEN\s*(\d+)", f_text)
        if m:
            w_gen = int(m.group(1))
            year = 2021 + w_gen
            break
        # 25. Qualcomm XR
        m = re.search(r"XR(\d+)\s*(?:GEN\s*(\d+))?", f_text)
        if m:
            xr = int(m.group(1))
            xr_gen = m.group(2)
            if xr_gen:
                year = 2020 + int(xr_gen)
            elif xr >= 2:
                year = 2019
            else:
                year = 2018
            break
        # 26. Snapdragon 3-digit
        m = re.search(r"SNAPDRAGON\s+(\d{3})(\d?)", f_text)
        if m:
            sd_full = int(m.group(1))
            if sd_full >= 855:
                year = 2019
            elif sd_full >= 845:
                year = 2018
            elif sd_full >= 835:
                year = 2017
            elif sd_full >= 820:
                year = 2016
            elif sd_full >= 810:
                year = 2015
            elif sd_full >= 800 or sd_full >= 600:
                year = 2014
            elif sd_full >= 400:
                year = 2013
            else:
                year = 2012
            break
        # 27. Qualcomm QSD
        m = re.search(r"\bQSD(\d{4})\b", f_text)
        if m:
            year = 2009
            break
        # 28. Qualcomm SW
        m = re.search(r"\bSW(\d{4})\b", f_text)
        if m:
            sw = int(m.group(1))
            year = 2015 + (sw // 1000)
            break
        # 29. Qualcomm CE
        m = re.search(r"\bCE(\d{4})\b", f_text)
        if m:
            ce = int(m.group(1))
            year = 2008 + (ce // 1000)
            break
        # 30. TI OMAP
        m = re.search(r"\bOMAP(\d)\d{3}\b", f_text)
        if m:
            omap_gen = int(m.group(1))
            year = 2004 + omap_gen * 2
            break
        # 31. Allwinner A/H/F/R prefix
        m = re.search(r"\b([AHFR])(\d{2,3})", f_text)
        if m:
            aw_prefix = m.group(1)
            aw_num = int(m.group(2))
            if aw_prefix == "F":
                year = 2015 if aw_num >= 100 else 2013
            elif aw_prefix == "R":
                year = 2012 + (aw_num // 10) if aw_num >= 40 else 2014
            elif aw_prefix == "H":
                if aw_num >= 700:
                    year = 2018 + (aw_num - 700) // 2
                elif aw_num >= 600:
                    year = 2015 + (aw_num - 600) // 2
                elif aw_num >= 500:
                    year = 2017 + (aw_num - 500) // 2
                elif aw_num >= 300:
                    year = 2014 + (aw_num - 300) // 2
                else:
                    year = 2013
            elif aw_prefix == "A":
                if aw_num >= 100:
                    year = 2014 + (aw_num - 100) // 10
                elif aw_num >= 80:
                    year = 2014
                elif aw_num >= 40:
                    year = 2015
                elif aw_num >= 31:
                    year = 2013
                elif aw_num >= 20 or aw_num >= 13:
                    year = 2012
                elif aw_num >= 10:
                    year = 2011
                else:
                    year = 2011 + aw_num // 5
            break
        # 32. Amlogic S-prefix
        m = re.search(r"\bS(\d{3})", f_text)
        if m:
            aml = int(m.group(1))
            if aml >= 928:
                year = 2020
            elif aml >= 922:
                year = 2019
            elif aml >= 912 or aml >= 905:
                year = 2016
            elif aml >= 812:
                year = 2015
            elif aml >= 805:
                year = 2014
            elif aml >= 802:
                year = 2013
            else:
                year = 2012
            break
        # 33. Amlogic T-prefix (vendor-gated)
        if chip.get("vendor") == "Amlogic":
            m = re.search(r"\bT(\d{3})", f_text)
            if m:
                aml_t = int(m.group(1))
                if aml_t >= 960:
                    year = 2016
                elif aml_t >= 950:
                    year = 2015
                elif aml_t >= 920:
                    year = 2018
                else:
                    year = 2014
                break
        # 34. MediaTek Kompanio
        m = re.search(r"KOMPANIO\s*(\d+)", f_text)
        if m:
            komp = int(m.group(1))
            if komp >= 1300 or komp >= 1200 or komp >= 800:
                year = 2022
            elif komp >= 500:
                year = 2021
            else:
                year = 2020
            break
        # 35. Intel Atom D/N prefix
        m = re.search(r"ATOM\s+([DN])(\d{4})", f_text)
        if m:
            atom_letter = m.group(1)
            atom_digits = int(m.group(2))
            year = 2010 + (atom_digits // 1000) if atom_letter == "D" else 2009 + (atom_digits // 500)
            break
        # 36. Ingenic JZ
        m = re.search(r"\bJZ(\d{4})\b", f_text, re.IGNORECASE)
        if m:
            jz = int(m.group(1))
            year = 2005 + (jz // 1000)
            break
        # 37. Qualcomm THOR
        m = re.search(r"\bTHOR\b", f_text)
        if m:
            year = 2025
            break
        # 38. Allwinner F1C/F1E
        m = re.search(r"F1[CE](\d{3})", f_text)
        if m:
            f1 = int(m.group(1))
            year = 2014 + (f1 // 100)
            break
        # 39. Qualcomm AIOT I
        m = re.search(r"AIOT\s*[Ii](\d{3})", f_text)
        if m:
            year = 2020 + (int(m.group(1)) // 100)
            break
        # 40. Spreadtrum SP
        m = re.search(r"\bSP(\d{4})\b", f_text)
        if m:
            sp = int(m.group(1))
            year = 2010 + (sp - 9000) // 100
            break
        # 41. Qualcomm UMS
        m = re.search(r"\bUMS(\d{4})\b", f_text)
        if m:
            ums = int(m.group(1))
            year = 2018 + ((ums - 9000) // 200)
            break
        # 42. HiSilicon K3V2
        m = re.search(r"\bK3V2", f_text)
        if m:
            year = 2012
            if "K3V2E" in f_text:
                year = 2013
            break
        # 43. HiSilicon Kirin T-prefix
        m = re.search(r"\bT(\d{2,3})", f_text)
        if m and "KIRIN" in f_text:
            kt = int(m.group(1))
            if kt >= 92:
                year = 2025
            elif kt >= 91:
                year = 2024
            elif kt >= 90:
                year = 2023
            elif kt >= 80:
                year = 2020
            break
        if year:
            break
    return year
