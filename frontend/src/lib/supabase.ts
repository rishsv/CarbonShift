import { createClient } from '@supabase/supabase-js';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || 'https://mock.supabase.co';
const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY || 'mock-key';

// This acts as a real client if env vars are provided, otherwise it's a dummy
export const supabase = createClient(supabaseUrl, supabaseKey);
