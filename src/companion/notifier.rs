pub struct Notifier {
    _app_name: String,
}

impl Notifier {
    pub fn new(app_name: impl Into<String>) -> Self {
        Self {
            _app_name: app_name.into(),
        }
    }

    pub fn send(&self, _title: &str, _body: &str) {}
}
