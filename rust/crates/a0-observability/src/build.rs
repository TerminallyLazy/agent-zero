use a0_core::BuildInfo;

pub fn build_info() -> BuildInfo {
    BuildInfo {
        version: env!("CARGO_PKG_VERSION").to_string(),
        commit: option_env!("GIT_COMMIT_SHA").map(ToString::to_string),
    }
}
