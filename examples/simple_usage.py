from pathlib import Path

from archive_kit import (
    PasswordPolicy,
    PasswordStrategy,
    batch_result_to_dict,
    batch_unpack,
    inspect_one,
    list_member_paths,
    member_exists,
    probe_support,
    read_member_text,
    unpack_one,
    write_batch_report_json,
)


if __name__ == "__main__":
    print(probe_support())

    password_policy = PasswordPolicy(
        passwords=("secret",),
        missing_password_strategy=PasswordStrategy.SKIP,
        invalid_password_strategy=PasswordStrategy.SKIP,
    )

    sample_archive = Path("./demo.tar.gz")
    if sample_archive.exists():
        print(inspect_one(sample_archive, recursive=True, profile="balanced"))
        print(list_member_paths(sample_archive, recursive=False))
        print(member_exists(sample_archive, "README.txt"))
        print(read_member_text(sample_archive, "README.txt", errors="ignore"))
        print(unpack_one(sample_archive, profile="balanced", password_policy=password_policy))

    sample_dir = Path("./input")
    if sample_dir.exists():
        result = batch_unpack(
            sample_dir,
            target_dir="./output",
            profile="balanced",
            password_policy=password_policy,
        )
        print(batch_result_to_dict(result))
        print(write_batch_report_json(result, "./output/archive-report.json"))
