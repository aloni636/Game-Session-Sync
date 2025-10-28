import random
from time import sleep

from win11toast import notify, update_progress

rng = random.Random(42)



def demonstrate_multi_progress():
    def build_xml(attribution="", url="") -> str:
        return """
            <toast activationType="protocol" launch="{url}" duration="short">
            <visual>
                <binding template="ToastGeneric">
                <text>Main Text</text>
                <text placement="attribution">{attribution}</text>
                </binding>
            </visual>
            </toast>
        """.format(
            attribution=attribution, url=url
        )

    tag_progress = {"A": {"max": 7, "current": 0}, "B": {"max": 15, "current": 3}}

    # create notifications
    for tag, progress in tag_progress.items():
        xml = build_xml("Click to open note in Notion")
        tag_max = progress["max"]
        tag_current = progress["current"]
        notify(
            xml=xml,
            progress={
                "title": "title...",
                "status": "status...",
                "value": tag_current / tag_max,
                "valueStringOverride": "value string override...",
            },
            tag=tag,
        )

    tags = list(tag_progress.keys())
    while True:
        if len(tags) == 0:
            break
        tag = rng.choice(tags)
        progress = tag_progress[tag]

        if progress["current"] >= progress["max"]:
            tags.remove(tag)
            continue
        progress["current"] += 1
        update_progress(
            progress={
                "title": "title...",
                "status": "status...",
                "value": progress["current"] / progress["max"],
                "valueStringOverride": "value string override...",
            },
            tag=tag,
        )
        sleep(1)


if __name__ == "__main__":
    demonstrate_multi_progress()
