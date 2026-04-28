import pymongo
import json

def initialize_templates():
    client = pymongo.MongoClient("mongodb://localhost:27017/")
    db = client["pga_worldview"]
    collection = db["worldview_templates"]
    
    templates = [
        {
            "category": "faction",
            "name_zh": "势力",
            "template": {
                "name": "[势力名称]",
                "type": "Empire | Federation | Alliance | Syndicate | Cult | Others",
                "ideology": "[核心意识形态/纲领]",
                "territory": ["[星区1]", "[星区2]"],
                "pga_compliance": "[如何解读或违反PGA协议]",
                "key_resources": ["[资源1]", "[资源2]"],
                "capital_star": "[首都星/主星系]"
            },
            "example": {
                "name": "极光联邦",
                "type": "Federation",
                "ideology": "技术民主主义，主张全人类热力学权利平等",
                "territory": ["天琴座Alpha", "织女星边境"],
                "pga_compliance": "严格遵守PGA-01协议，禁止任何形式的时间实验",
                "key_resources": ["零点能集束器", "重水矿"],
                "capital_star": "诺亚之光"
            }
        },
        {
            "category": "race",
            "name_zh": "种族",
            "template": {
                "name": "[种族名称]",
                "biological_type": "Carbon-based | Mechanical | Energy | Silicon-based",
                "entropy_efficiency": "[能耗与熵效率描述]",
                "ecological_niche": "[在星区生态系统中的地位]",
                "evolutionary_history": "[演化历程简述]",
                "special_abilities": ["[能力1]", "[能力2]"]
            },
            "example": {
                "name": "熵族",
                "biological_type": "Energy",
                "entropy_efficiency": "极高，能够直接摄取高熵废料转化为动能",
                "ecological_niche": "星系清道夫，负责平衡被废弃星区的熵值",
                "evolutionary_history": "诞生于第一次大湮灭后的高能辐射海",
                "special_abilities": ["物质分解", "热寂免疫"]
            }
        },
        {
            "category": "geography",
            "name_zh": "地理环境",
            "template": {
                "name": "[环境名称]",
                "type": "Star Cluster | Nebula | Dyson Sphere | Void Area",
                "gravity_level": "[重力等级G]",
                "entropy_index": "0.0 - 1.0 (Order to Chaos)",
                "resource_density": "Low | Medium | High",
                "notable_anomalies": ["[异常1]", "[异常2]"]
            },
            "example": {
                "name": "克洛斯星云",
                "type": "Nebula",
                "gravity_level": "0.2G (平均)",
                "entropy_index": "0.85 (高度不稳定)",
                "resource_density": "High",
                "notable_anomalies": ["时空曲率波", "电磁死区"]
            }
        },
        {
            "category": "religion",
            "name_zh": "宗教",
            "template": {
                "name": "[宗教名称]",
                "deity": "[崇拜对象/实体]",
                "core_belief": "[核心信条，通常涉及熵或PGA]",
                "rituals": "[主要祭祀/仪式]",
                "influence_range": "[势力范围]",
                "holy_sites": ["[圣地1]"]
            },
            "example": {
                "name": "圣热力学教派",
                "deity": "第一推动力 (The First Mover)",
                "core_belief": "生命存在的唯一意义是延缓宇宙热寂",
                "rituals": "能量献祭仪式",
                "influence_range": "银河系核心星区",
                "holy_sites": ["太阳神殿"]
            }
        },
        {
            "category": "crisis",
            "name_zh": "危机",
            "template": {
                "name": "[危机名称]",
                "type": "Entropy Surge | War | Plague | Tech-Collapse",
                "severity": "1-10",
                "affected_entities": ["[受影响势力1]", "[受影响种族1]"],
                "causality": "[起因与后果链条]",
                "current_status": "Dormant | Active | Resolved"
            },
            "example": {
                "name": "零点能泄露事故",
                "type": "Tech-Collapse",
                "severity": "9",
                "affected_entities": ["极光联邦", "天琴座殖民地"],
                "causality": "因超负荷开采导致的局部时空撕裂",
                "current_status": "Active"
            }
        },
        {
            "category": "weapon",
            "name_zh": "武器",
            "template": {
                "name": "[武器名称]",
                "operating_principle": "[物理运作原理]",
                "energy_source": "[能源形式]",
                "destructive_yield": "[破坏力等级]",
                "pga_legal_status": "Legal | Restricted | Forbidden",
                "side_effects": "[对环境的负面影响]"
            },
            "example": {
                "name": "熵增散弹枪",
                "operating_principle": "通过发射局部熵加速粒子，使目标分子结构瞬间解体",
                "energy_source": "便携式熵核",
                "destructive_yield": "单点战术级",
                "pga_legal_status": "Restricted",
                "side_effects": "留下的区域会产生长时间的熵云污染"
            }
        },
        {
            "category": "creature",
            "name_zh": "生物野兽",
            "template": {
                "name": "[生物名称]",
                "habitat": "[栖息地环境]",
                "predation": "[捕食方式]",
                "danger_level": "E | D | C | B | A | S",
                "biological_advantage": ["[优势1]", "[优势2]"],
                "weakness": "[弱点描述]"
            },
            "example": {
                "name": "虚空掠食者",
                "habitat": "星际间隙的暗物质云",
                "predation": "吸食过往飞船的能量溢出",
                "danger_level": "A",
                "biological_advantage": ["透明躯体", "相位穿梭"],
                "weakness": "高频率超声波"
            }
        },
        {
            "category": "planet",
            "name_zh": "星球",
            "template": {
                "name": "[星球名称]",
                "classification": "Terrestrial | Gas Giant | Ice Giant | Artificial",
                "atmosphere_composition": "[大气成分]",
                "surface_conditions": "[温度、重力、气候]",
                "dominant_species": "[主要居住种族]",
                "notable_landmarks": ["[地标1]", "[地标2]"]
            },
            "example": {
                "name": "阿卡迪亚",
                "classification": "Terrestrial",
                "atmosphere_composition": "78% 氮气, 21% 氧气, 1% 稀有气体",
                "surface_conditions": "平均25℃，1.05G，常年微雨",
                "dominant_species": "人类",
                "notable_landmarks": ["悬浮议会大厦", "水晶大瀑布"]
            }
        },
        {
            "category": "organization",
            "name_zh": "组织",
            "template": {
                "name": "[组织名称]",
                "parent_entity": "[所属势力]",
                "objective": "[行动目标]",
                "membership": "[成员规模/特征]",
                "funding": "[资金/资源来源]",
                "legal_status": "Legal | Underground | Rogue"
            },
            "example": {
                "name": "暗影观测者",
                "parent_entity": "中立",
                "objective": "监控星系间的黑洞活动",
                "membership": "顶级物理学家与黑客",
                "funding": "匿名跨国资助",
                "legal_status": "Legal"
            }
        },
        {
            "category": "technology/mechanism",
            "name_zh": "科技/机制",
            "template": {
                "name": "[名称]",
                "physics_laws": "[遵循的物理定律/热力学解读]",
                "working_principle": "[运作原理]",
                "energy_source": "[能源来源]",
                "limitations": "[技术局限/副作用]",
                "origin": "[研发背景/势力]"
            },
            "example": {
                "name": "反物质发动机",
                "physics_laws": "遵循质能方程 E=mc²，需严格磁力约束防止湮灭导致的热力学系统崩溃。",
                "working_principle": "通过正负物质湮灭释放的高能光子推动等离子体工质。",
                "energy_source": "反氢燃料颗粒",
                "limitations": "磁场发生器耗能极高，探测器极易受到湮灭热量干扰。",
                "origin": "半人马座阿尔法星研究所"
            }
        },
        {
            "category": "history/events",
            "name_zh": "历史事件",
            "template": {
                "name": "[事件名称]",
                "time_period": "[发生时间/星历]",
                "involved_factions": ["[参与势力1]", "[参与势力2]"],
                "key_figures": ["[关键人物1]", "[关键人物2]"],
                "cause": "[起因]",
                "outcome": "[结果/条约]",
                "impact": "[对宇宙格局的长远影响]"
            },
            "example": {
                "name": "第一次星界战争",
                "time_period": "星历 4421年 - 4455年",
                "involved_factions": ["地球联邦", "奥族圣所"],
                "key_figures": ["上将 陈风", "大祭司 萨维尔"],
                "cause": "对奥利安星区零点能矿脉的争夺。",
                "outcome": "签署《停战协议》，奥利安星区设为中立贸易区。",
                "impact": "导致了地球联邦内部的政治大清洗，以及奥族圣所向隐遁主义的转型。"
            }
        }
    ]

    
    # 清空旧模板以防冲突，重新插入
    collection.delete_many({})
    collection.insert_many(templates)
    print(f"Successfully initialized {len(templates)} templates in 'worldview_templates' collection.")

if __name__ == "__main__":
    try:
        initialize_templates()
    except Exception as e:
        print(f"Error: {e}")
